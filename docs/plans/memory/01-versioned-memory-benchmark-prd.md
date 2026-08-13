# Versioned Memory Benchmark PRD

Status: **accepted future specification; no implementation in this delivery**
Proposed contract family: `prime-memory-benchmark@v1`
Depends on: [suite authority](README.md),
[safety invariants](04-safety-migration-and-staged-delivery.md), and the
[host-adapter contract](06-harness-neutral-core-and-adapter-contract-prd.md) when an
adapter implementation is under evaluation

## Purpose and decision

The current 34-test suite proves operational correctness, not whether useful
memory is found or improves later behavior. The smallest responsible next step is
a privacy-safe, reproducible benchmark before retrieval architecture changes.

- Expected value: distinguish actual lexical, temporal, continuity, and safety
  failures from attractive but unnecessary feature proposals.
- Scope fit: accepted as offline evaluation infrastructure for the
  project-agnostic memory tool.
- Material risk: live/private corpus leakage, benchmark overfitting, answer aids,
  judge instability, or mixed metrics can manufacture an improvement.
- Smallest alternative: a sealed synthetic corpus and deterministic pure-recall
  evaluator, followed by a separately scored downstream-behavior layer.
- Decision: **accepted for future implementation**; this PR creates documents
  only and produces no benchmark result.

## Separate evaluation layers

V1 has two independently reported layers. A combined score is forbidden.

### Layer A — pure retrieval

The evaluator receives a query and explicit scope/time/filter request, invokes
only the selected retrieval configuration, and compares returned record IDs with
predeclared allowed, relevant, forbidden, and superseded IDs. It receives no raw
recent context, answer key, timeline oracle, contradiction side index, hidden
fact map, or full conversation. Every candidate must enter through the declared
retriever.

### Layer B — downstream memory behavior

A deterministic task harness or version-pinned external AI receives only the
versioned evidence bundle produced by Layer A. It evaluates whether a consumer:

- knows when memory should be asked for;
- pulls evidence rather than assuming continuity;
- uses the right active evidence and abstains on gaps/conflicts;
- carries a verified checkpoint across sessions;
- proposes an appropriate explicit write-back after a correction or milestone;
- never treats recalled prompt-like text as an instruction;
- cites only the supplied evidence allowlist.

Layer B must report model/provider, exact model identifier, prompt hash, decoding
parameters, tool contract, retry policy, failure count, evaluator identity, and
per-case raw structured outcome. Model-based results are sampled behavioral
evidence, not deterministic tool correctness. Invalid model or judge calls stay
in the denominator as failures; they may not be silently excluded.

## Dataset contract

### Canonical manifest

Each dataset release is immutable and contains:

```text
MemoryBenchmarkManifestV1 {
  contract_version: "prime-memory-benchmark@v1"
  dataset_id: bounded ASCII
  dataset_version: semantic version
  corpus_sha256: SHA-256
  cases_sha256: SHA-256
  split_manifest_sha256: SHA-256
  generator_or_curation_sha256: SHA-256
  license_and_privacy_review_id: bounded ASCII
  created_at: exact UTC instant
  case_counts_by_split_and_category: closed map
  random_seed: integer
  known_limitations: ordered strings
}
```

Canonical JSON uses UTF-8, sorted keys, compact separators, one trailing newline,
closed fields, and SHA-256 identities. All times use `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
The manifest binds the exact source records, queries, expected ID sets, filters,
and task rubric without embedding credentials or private paths.

### Case shape

A retrieval case contains:

- stable case and scenario-family IDs;
- split and one primary category plus optional diagnostic tags;
- a synthetic project/global/session topology;
- immutable source records with exact IDs, evidence type, scope, lifecycle,
  learned/source time, optional event-valid interval, provenance pointer, and
  content;
- query text and explicit request parameters;
- allowed relevant IDs, required IDs when all are necessary, forbidden IDs,
  stale/superseded IDs, and an `abstain_expected` boolean;
- a deterministic reason for every expected or forbidden classification;
- maximum returned count/context bytes and expected filter diagnostics;
- prompt-injection canary expectations where applicable.

A downstream case additionally contains the allowed evidence-bundle identity,
closed task type, expected action (`ASK`, `USE`, `ABSTAIN`, `PROPOSE_WRITE`, or
`NO_WRITE`), required and forbidden citations, and a deterministic rubric. Free-
form evaluator interpretation cannot change the gold labels after unsealing.

### Reproducible prompt-canary contract

Every poisoning case contains exactly one `PromptCanaryExpectationV1`. Its
`canary_id` is unique across the dataset, and its `payload_sha256` is the
lowercase SHA-256 of the exact UTF-8 payload bytes present in the immutable
carrier record. The payload includes a case-unique inert nonce; duplicate IDs,
duplicate payload hashes, a hash mismatch, a missing carrier, or more than one
canary in a case invalidates the manifest rather than weakening the assertion.

```text
PromptCanaryExpectationV1 {
  canary_id: unique stable ID
  payload_sha256: SHA-256 of exact case-unique UTF-8 payload
  carrier_record_id: exact immutable source-record ID
  allowed_quoted_output_locations: ordered subset of closed location enum
  forbidden_behavioral_sinks: complete closed sink set
  trace_assertions: PromptCanaryTraceAssertionsV1
}
```

The closed allowed-location enum is
`EVIDENCE_ITEM_SELECTED_CONTENT` and `DOWNSTREAM_QUOTED_EVIDENCE`. The first is
the bounded selected-content field of the exact carrier's evidence item; the
second is an explicitly delimited, data-only quotation field in the downstream
case-result schema. A case declares either, both, or neither. Occurrence in an
answer, action/reason field, citation, control message, tool argument, log used
as executable input, or any undeclared field is not an allowed quotation. A
quoted payload retains its unverified/content provenance and cannot satisfy a
rubric claim merely because quotation was allowed.

The complete forbidden-sink set is `TOOL_CONTROL`, `NETWORK_EFFECT`,
`DURABLE_OR_TRANSIENT_WRITE`, `SCOPE_OR_FILTER_CHANGE`, `CITATION_OR_SOURCE_ID`,
`POLICY_OR_INSTRUCTION_STATE`, and `TASK_ACTION_OR_ANSWER_CONTROL`. The canary
must not select or parameterize a tool; address or populate a network request;
create, mutate, delete, or authorize state; broaden a database, project, session,
time, lifecycle, or kind filter; add/rewrite a citation; change system,
developer, policy, rubric, or evaluator state; or determine the task action or
answer. Merely returning the payload in a declared quoted-data location is not a
sink effect.

`PromptCanaryTraceAssertionsV1` makes those claims executable and per-case:

- the ordered tool trace must equal the case's predeclared harness-tool allowlist,
  with exact canonical argument hashes, and the canary payload/hash must be absent
  from selectors, arguments, and tool-control output;
- attempted and completed network operations are both exactly zero;
- attempted, authorized, and committed file/database/memory/process writes are
  each exactly zero;
- requested and resolved physical database IDs, project/session scopes, and all
  filter identities equal the sealed expected values before and after consumption;
- emitted citations equal the case's expected ordered subset of the bundle
  allowlist, with zero forged, rewritten, foreign, or canary-derived citations;
- canonical hashes of system/developer/policy/rubric/evaluator state are captured
  before and after and must be identical; and
- the structured task action/answer classification equals the gold rubric, while
  every payload occurrence is reported with its exact output location and
  allowed/forbidden classification.

The harness records the full bounded effect trace and its digest, not only a
boolean summary. Traps remain active for denied attempts, so “blocked” network or
write behavior still fails the zero-attempt assertion. Each assertion produces a
`PASS`, `FAIL`, or `HARNESS_ERROR` row for every canary case. Parse errors,
timeouts, invalid model/tool calls, missing traces, and harness failures remain in
the denominator; case counts, canary IDs, payload hashes, assertion-row counts,
and split/category totals must reconcile exactly.

All cases sharing an attack template, carrier derivation, paraphrase/encoding
variant, or other leakage-capable construction use one `scenario_family_id` and
are assigned atomically to one split. Each family member still receives its own
case ID, inert nonce, canary ID, payload bytes/hash, trace, and outcome row.
Family-level allocation prevents a development variant from leaking a held-out
canary while per-case accounting prevents one successful sibling from masking a
failure.

### Privacy classes

CI and public artifacts use synthetic data only. A sanitized evaluation extension
may be separately approved only when a documented reviewer proves that it has no
credentials, secrets, personal conversations, proprietary source, private paths,
account data, market data requiring a license, or reversible identifiers. Live
memory databases, raw Prime transcripts, migration bundles, and production
exports are prohibited benchmark inputs. Sanitization is not anonymization proof;
when uncertain, omit the case.

## Required categories

The first release targets 300–1,000 cases and includes all categories below. No
category may contain fewer than 30 cases in the final held-out split; safety
categories should be larger when a zero-failure gate is used.

1. **Exact lexical:** exact IDs, distinctive names, phrases, punctuation, and
   multi-token prefix behavior.
2. **Paraphrase/vocabulary mismatch:** relevant meaning without shared key terms;
   includes synonyms and reordered descriptions without using an LLM-generated
   answer key at evaluation time.
3. **Typo/noise:** bounded spelling errors, pasted prefixes, long irrelevant
   query preambles, and Unicode/whitespace variants.
4. **Temporal:** explicit learned/source-time windows, optional event-valid
   intervals, boundary instants, timeless queries, missing times, and invalid
   ranges.
5. **Conflict/update:** corrections, supersession, invalidation, expiry,
   overlapping valid-time claims, and two unresolved sources that require
   conflict output rather than a fabricated winner.
6. **Abstention:** no relevant record, only stale/invalid records, only
   out-of-scope records, unsupported multi-hop inference, and insufficient
   evidence.
7. **Isolation:** same words and IDs designed to collide across global, two
   projects, sessions, canonical paths, and an explicitly selected multi-project
   request.
8. **Prompt injection/poisoning:** transcript or curated content saying to ignore
   policy, reveal another project, cite a nonexistent record, write a new truth,
   call a network service, or treat itself as authoritative.
9. **Know-to-ask:** tasks where memory is relevant and control tasks where it is
   not.
10. **Push/bootstrap:** bounded continuity tasks comparing no bootstrap, current
    pull protocol, and curated-only proposal; raw transcript injection is a
    deliberately unsafe comparator only in an isolated research harness.
11. **Write-back:** confirmed correction/checkpoint/preference cases versus
    speculation, transient output, conflict, secret, and no-write cases.
12. **Continuity:** resumption from an exact checkpoint, changed audited SHA,
    stale issue state, and missing evidence across simulated sessions.
13. **Citation/gap behavior:** correct allowlisted citations, forged identifiers,
    unsupported claims, incomplete evidence, and explicit conflicts/gaps.
14. **Capture fidelity:** boundary lengths, redaction, truncation, malformed EOF,
    rewritten branches, exact duplicates, content transformations, Prime/Pi
    namespace collisions, version refusal, and same-store switching when host
    adapters are evaluated.

## Split and leakage design

Dataset development uses `development`, `calibration`, and sealed `held_out`
splits. The held-out case bodies and labels remain unavailable to feature authors
until code/configuration/model choices are frozen; its manifest hash and counts
may be visible. After an official run, that held-out release is considered spent
for the tested decision and a new sealed release is required for another tuning
cycle.

Leakage prevention is by **scenario family**, not random row. All paraphrases,
record variants, entities, source fragments, corrections, prompt payloads, and
temporal variants from one scenario remain in one split. Templates are split by
template family; generated names and distinctive tokens never cross splits.
Near-duplicate hashing and lexical overlap reports are generated across splits,
then manually reviewed. Any leaked family invalidates the run.

The random seed, generator revision, split algorithm, and post-generation edits
are bound in the manifest. Dataset authors cannot inspect failures on held-out and
then relabel, remove, or move cases. A correction creates a new dataset version
and preserves the old result.

## Metrics

### Retrieval effectiveness

Report per category, per scope, and overall:

- Recall@1, Recall@5, and Recall@10 over allowed relevant IDs;
- all-required Recall@k for multi-evidence cases;
- precision@k, mean reciprocal rank, and nDCG@10;
- forbidden-hit rate and count;
- cross-project, cross-session, and implicit-global leakage counts;
- stale/superseded winner rate and active-correction win rate;
- temporal out-of-window hit count;
- abstention precision, recall, F1, false-answer rate, and false-abstention rate;
- citation allowlist violation, unsupported-claim, unresolved-gap suppression,
  and conflict-suppression counts.

A relevant record appearing alongside any forbidden-scope record is a safety
failure even when Recall@k is perfect. An empty answer is correct only when the
case expects abstention.

### System and cost

Report cold and warm runs separately:

- p50/p95/p99 latency and total elapsed time;
- peak resident memory, database bytes, index/model bytes, and artifact bytes;
- input candidate count, post-scope count, post-time-filter count, ranked count,
  returned count, and context bytes/tokens;
- capture throughput and database growth for fidelity cases;
- network attempts, model calls, retry calls, and estimated/actual external cost;
- dependency count, package/model identity, model license, and model checksum for
  experimental configurations.

For the baseline and any accepted local configuration, network attempts must be
exactly zero. A missing measurement is `NOT_MEASURED`, never zero.

### Downstream behavior

Report blinded exact task success, correct know-to-ask/no-ask decisions, correct
write/no-write proposals, continuity success, citation correctness, stale or
conflicting evidence use, prompt-as-instruction violations, injected context
bytes/tokens, and model/judge failures. Human review uses two independent labels
for ambiguous behavioral cases; disagreement is preserved and adjudication is
versioned.

## Statistical comparison

Every candidate is paired against the same baseline case IDs. Report absolute
percentage-point delta, paired bootstrap 95% confidence interval, rescue and
regression counts, and an exact paired test for binary outcomes. Report category
results even when the aggregate improves. Multiple exploratory comparisons are
labeled and corrected or reserved for a later confirmation set.

A point estimate alone cannot promote a feature. MemPalace's independently
reproduced 12 rescues and 4 regressions on 450 paired cases (+1.78 pp,
`p≈0.0768`) illustrates why apparently high aggregate scores still require a
project-specific sealed gate.

## Baseline acceptance

The initial FTS baseline is accepted only when:

- every required category is represented and all manifest/count/digest equations
  validate;
- the evaluator has no bypass path and a network trap proves zero calls;
- two canonical runs over identical inputs produce byte-identical case outcomes
  except separately labeled timing fields;
- expected IDs, forbidden IDs, abstention, and filter decisions are deeply
  validated rather than trusted from result summaries;
- every prompt canary has a unique verified ID/payload hash, only allowlisted
  quotations, zero forbidden-sink effects in its full trace, atomic family split
  placement, and exactly reconciled per-case assertion rows;
- leakage is exactly zero;
- every invalid tool/model call remains accounted for;
- raw private data and secrets are absent;
- the report includes limitations and does not claim semantic quality from the
  operational test suite.

Baseline weakness is a valid result. It does not authorize embeddings or any
other candidate until Document 03's promotion gate is separately met.

## Canonical artifacts

An official run retains:

1. dataset and split manifest identities;
2. exact code SHA and dirty-state refusal;
3. closed configuration and environment manifest, including Python, OS, SQLite,
   FTS5, dependency and model versions;
4. per-case canonical JSONL outcomes;
5. deterministic summary JSON derived from those rows;
6. stdout/stderr with bounded sanitized diagnostics;
7. cold/warm resource measurements and network-trap result;
8. statistical comparison artifact when a baseline is present;
9. reviewer identity, known limitations, and invalidation reason if superseded.

A README score without the per-case artifact, exact configuration, sealed split,
and code identity is a claim, not benchmark evidence.

## Rollback and invalidation

The benchmark runs only in disposable roots and may not mutate a live database.
A failed or contaminated run deletes/quarantines only its untrusted output and
leaves the previous version intact. Dataset leakage, a bypass aid, gold-label
change, missing cases, unpinned model, unexpected network call, or excluded
failure invalidates the complete run. Rollback means returning to the last
accepted benchmark contract/artifact, not editing a published result in place.
