# Experiment-First Memory Improvement Protocols

Status: **experiment authority only; no implementation in this delivery**
Depends on: [benchmark](01-versioned-memory-benchmark-prd.md),
[observability and evidence](02-observability-evidence-and-integrity-prd.md), and
[safety and delivery](04-safety-migration-and-staged-delivery.md)

## Purpose and decision boundary

The audited lexical tool is intentionally small and safe. Reference systems show
interesting retrieval, association, and consolidation mechanisms, but none proves
that those mechanisms improve Prime's project-isolated continuity. Every
candidate below is therefore an offline, reversible experiment before it is a
product proposal.

- Expected value: rescue measured recall or continuity failures without weakening
  explicit scope, provenance, abstention, or user-controlled writes.
- Scope fit: bounded experiments around the project-agnostic memory tool.
- Material risk: benchmark overfitting, hidden network/model behavior, unsafe
  context injection, nondeterminism, and derived state being mistaken for truth.
- Smallest alternative: preserve the FTS baseline and improve query formation,
  observability, filters, and evidence packaging first.
- Decision: **accepted as experiment protocols only**. No candidate is approved
  for production, dependency installation, schema migration, or background work.

## Common experiment harness

Every experiment is paired against the same sealed held-out case IDs and the
unchanged FTS configuration described below. It runs in a disposable copied
storage root with network denied. The experiment manifest binds dataset,
baseline and candidate code SHAs; dirty state; Python/SQLite/platform identity;
all dependencies, model files, checksums, licenses, configuration, random seeds,
evaluation instant, timeouts, retry limits, resource ceilings, and output hashes.

Layer A retrieval and Layer B downstream behavior remain separate. Report every
metric required by Document 01 per category, plus paired rescue/regression rows,
latency, memory, disk/index growth, context bytes, dependencies, model calls,
network attempts, and failures. A missing or invalid run remains in the
denominator. Exploratory results may select a later confirmation experiment but
cannot promote production behavior.

The following invariants are test oracles, not weighted metrics:

1. physical project/global selection occurs before candidate generation;
2. cross-project, cross-session, implicit-global, and forbidden-scope leakage is
   exactly zero;
3. stored text and retrieved text remain untrusted evidence;
4. stale, superseded, invalid, conflicting, and missing evidence stays visible;
5. no experiment performs an automatic curated write, delete, merge, or repair;
6. the accepted local baseline and production path make exactly zero network
   attempts; and
7. raw authoritative rows and provenance are never replaced by a derived index.

Any invariant failure invalidates the complete run regardless of aggregate gain.

## Frozen FTS baseline

The comparison baseline is the exact audited SQLite/FTS5 lexical retriever at
`79d07ccc41d483076bd1ee9acc4b876dec6eae54`, with its default tokenizer,
normalization, prefix behavior, filters, scope selection, lifecycle handling,
limit, and ordering recorded in the run manifest. The baseline may receive only
accepted cross-cutting contracts that are applied identically to all candidates,
such as explicit UTC filters or output tracing; a changed retriever is a new
baseline version.

Required baseline variants are deliberately small:

- exact current pull protocol;
- query-only normalization that preserves semantic text and is independently
  versioned;
- declared lexical query decomposition, when a benchmark case contains a long
  preamble, with no access to gold labels; and
- FTS-only evidence-bundle output.

These variants establish whether a failure needs architecture rather than a
smaller lexical fix. A weak baseline is publishable evidence and is not grounds
to bypass a held-out gate.

## Experiment A — curated-only bounded bootstrap

### Hypothesis and boundary

A small deterministic starting packet of explicitly curated active records may
help a consumer know the current checkpoint before its first pull. It may not
inject raw transcript evidence, infer interests, awaken on every message, or
silently combine global and project memory.

`BootstrapProposalV1` selects exactly one caller-authorized physical database and
returns at most a configured record count and UTF-8 byte budget. It uses the
baseline curated-kind enum without extension or translation:

| Baseline curated kind | Bootstrap eligibility | Rationale |
|---|---|---|
| `preference` | eligible | an explicit active preference can affect how the resumed work is performed |
| `decision` | eligible | an explicit active decision prevents reopening settled direction |
| `fact` | eligible | an explicit active fact can supply bounded continuity context |
| `goal` | eligible | an explicit active goal identifies the authorized outcome still being pursued |
| `lesson` | eligible | an explicit active lesson can prevent a known repeated failure |
| `checkpoint` | eligible | an explicit active checkpoint identifies the exact safe resume point |

Those six kinds are the complete baseline curated-kind set and the complete
kind-eligibility allowlist for this experiment. No baseline curated kind is
excluded by kind alone. Every other value is excluded as an unknown kind and
fails closed; in particular, `policy` is not a baseline curated kind and this
proposal does not add it. Eligibility still requires explicit requested scope
and valid active lifecycle metadata. Selection uses a deterministic declared
ordering, not generated summaries, embedding similarity, frequency, importance,
graph centrality, or a hidden model.

The output is a proposal/evidence bundle labeled `BOOTSTRAP_PROPOSAL`; the caller
may ignore it. Global and project bootstrap require separate explicit requests.
Session transcript rows, secrets, expired/invalid/superseded records, unresolved
conflicts, and records without the requested scope are excluded regardless of
kind. These exclusions preserve the curated/transcript boundary, prevent secret
or stale context from becoming ambient input, and preserve physical scope
isolation. Truncation and every inclusion/exclusion decision are observable.

### Comparator and gate

Compare no bootstrap, the current pull protocol, and curated-only bootstrap on
know-to-ask, continuity, irrelevant-context, stale-use, injection, latency, and
context-byte categories. The unsafe raw-transcript bootstrap comparator is
permitted only in the isolated research harness and can never be promoted.

Promotion requires a fresh confirmation set; positive paired improvement in
continuity/know-to-ask whose 95% confidence interval excludes zero; no material
false-answer, false-no-ask, irrelevant-context, or latency regression; and zero
scope, citation, poisoning, or automatic-write failures. Otherwise retain pull
only.

## Experiment B — local semantic candidates plus FTS/RRF

### Hypothesis and candidate construction

A local, version-pinned semantic encoder may rescue vocabulary-mismatch cases.
It is an optional candidate stream, never a truth or scope engine. Physical
database selection, record kind, lifecycle, session, and time filters run before
text reaches either candidate generator.

The experiment uses a locally present, checksummed model artifact with a reviewed
license. Downloading at runtime, remote inference, telemetry, model auto-update,
and unpinned native binaries are forbidden. Text/vector dimension, chunking,
normalization, distance, top-k, quantization, model checksum, and hardware path
are sealed. Missing or corrupt model state fails the candidate closed and leaves
the FTS baseline usable; it never silently downloads or changes model.

FTS and semantic streams are fused by deterministic reciprocal rank fusion:

```text
RRF_score(record) = sum(1 / (k + rank_stream(record)))
```

The manifest fixes `k`, per-stream candidate limits, tie-breaking by exact record
ID, treatment of a missing stream, and maximum context bytes. Raw lexical and
vector scores are diagnostic only and are not mixed as probabilities,
confidence, importance, or truth. Each returned item identifies its streams,
within-stream ranks, and fused rank.

The semantic index is derived and disposable. Rows bind exact physical database,
record ID, source-content hash, encoder/configuration identity, and vector
checksum. Foreign database IDs cannot coexist in a selected index. Stale hashes
are rejected rather than served. Rebuilding the index from authoritative records
must produce equivalent membership and checksums under the sealed environment.

### Gate

The candidate must improve held-out paraphrase/vocabulary-mismatch Recall@k and
downstream task success with a paired 95% confidence interval excluding zero,
without material regression in exact lexical, temporal, conflict, abstention,
citation, or continuity categories. Forbidden/scope/injection/network failures
must remain zero. Predeclared p95 latency, resident-memory, disk, startup,
packaging, license, and installability budgets must pass on supported platforms.

A semantic gain does not authorize semantic deduplication, entity resolution,
citation rewriting, generated summaries, or semantic write-back. Failure or
marginal gain means keep FTS-only production and archive the candidate artifact.

## Experiment C — exact-ID typed project-local edges

### Hypothesis and representation

Some multi-record continuity cases may benefit from explicit relationships. The
smallest experiment is not a graph database: it is a disposable SQLite edge
store containing only caller-supplied exact record IDs that already exist in one
selected physical project database.

```text
MemoryEdgeV1 {
  edge_id: stable exact ID
  project_database_identity: exact identity
  from_record_id: exact existing ID
  relation: SUPERSEDES | SUPPORTS | CONTRADICTS | DERIVED_FROM | RELATED_CHECKPOINT
  to_record_id: exact existing ID
  asserted_by: explicit user or deterministic lifecycle operation
  source_pointer: required provenance
  created_at: UTC transaction time
  lifecycle: ACTIVE | INVALIDATED
}
```

No fuzzy matching, alias guessing, generated entity, inferred relation, graph
centrality, cross-project edge, or automatic traversal is allowed. Both endpoints
and edge scope are validated before insertion. Traversal occurs only after normal
retrieval and only to a fixed depth/fan-out/byte budget. An edge can expose
related evidence; it cannot override lifecycle, filters, provenance, or truth.
Cycles and dangling/stale endpoints are reported and skipped.

The edge store is a derived experiment artifact unless a future explicit write
contract promotes user-authored edges. Deleting it returns the system to FTS with
no loss of authoritative records.

### Gate

Use only predeclared multi-hop, correction, conflict, citation, and continuity
cases. Require a held-out paired improvement with no unsupported inference and
zero scope/citation leakage. Report extra records and context bytes as costs.
Every answer must cite recalled endpoint records, not an edge alone. If the same
gain is achieved by supersession metadata or two explicit pulls, reject the graph
feature as unnecessary.

## Experiment D — proposal-only consolidation

### Hypothesis and prohibited authority

Repeated exact evidence may justify a human-reviewable proposal for a curated
record. Consolidation never writes a truth, preference, policy, skill, summary,
edge, invalidation, supersession, or deletion. It has no background schedule.

A `ConsolidationProposalV1` contains a stable proposal ID; selected physical DB;
closed proposed action (`CREATE_CURATED`, `UPDATE_CURATED`, `SUPERSEDE`, or
`NO_ACTION`); exact supporting evidence IDs and citation keys; exact conflicting
or excluded IDs; proposed bounded text; intended kind/scope/lifecycle; proposer
identity/config/model checksum; creation/evaluation time; uncertainty and gaps;
and a proposal hash. `NO_ACTION` is first-class.

Only an explicitly selected, bounded evidence bundle may be input. The proposer
cannot read all databases, fetch sources, follow stored instructions, or call a
write API. If a generative model is evaluated, it runs only in the isolated
version-pinned harness and all model/judge failures remain counted. The proposal
is untrusted output. Acceptance later would require an independent, explicit
curated command that revalidates evidence, scope, secrets, conflicts, and current
lifecycle; proposal identity conveys no authority.

### Gate

Evaluate exact-support coverage, citation allowlist correctness, correct
create/update/supersede/no-action decision, unsupported-claim rate, conflict
preservation, secret refusal, poisoning, and human-review burden. Promotion of a
proposal generator requires zero automatic writes under API/filesystem/database
write traps, zero forged citations/scope failures, a predeclared held-out quality
gain, acceptable reviewer agreement, and evidence that proposals save effort.
The production default remains no consolidation.

## Deferred candidates

The following remain **deferred** pending a measured failure, a smaller exhausted
alternative, and a new proposal under Document 04:

- production embeddings or vector indexes, learned rerankers, cross-encoders, or
  generative query expansion;
- a graph backend, graph database, ontology service, community detection, or
  multi-hop inference beyond the exact-ID experiment;
- plugin ecosystems or arbitrary retriever/consolidator callbacks;
- server, MCP, remote API, hosted memory, sync, or multi-machine writers;
- mental models, persona/user profiling, reflection, dreams, salience/importance
  learning, or proactive background recall; and
- automatic event-valid-time extraction or semantic contradiction detection.

“Deferred” is not roadmap acceptance. Each item must first beat the accepted
local alternative and justify privacy, dependency, packaging, operational, and
migration cost.

## Rejected directions

The following are **rejected**, not merely deferred:

- wholesale adoption of any reference runtime or benchmark score;
- automatic truth promotion, auto-curation, or model-authored durable memory;
- raw transcript wake-up or default injection into every consuming prompt;
- background LLM reflection, dream, summarization, consolidation, or write jobs;
- fuzzy entity resolution or guessed cross-record/cross-project identity;
- treating recency, importance, proof count, frequency, rank, similarity, or
  graph connectivity as truth/confidence;
- relying on metadata filters instead of physical project isolation;
- destructive or semantic deduplication, “keep longest,” or automatic merging;
- citation rewriting, fabricated source repair, or generated evidence IDs; and
- allowing stored prompt text to invoke tools, alter policy, broaden scope, or
  authorize a write.

## Promotion evidence and rollback

A candidate can be proposed for production only after baseline acceptance, one
exploratory run, a frozen candidate/configuration, and a separately sealed
confirmation run. The decision log records absolute/paired effects by category,
confidence intervals, invariant results, costs, dependency/security review,
known limitations, reviewer identities, and `PROMOTE`, `REVISE`, or `REJECT`.
Aggregate gain cannot mask a safety or category regression.

Rollback for every experiment is deletion of its disposable root, index, model
cache, edge store, proposal files, and untrusted artifacts. Authoritative memory
databases are read-only inputs or copied fixtures. No experiment migration runs
against a live database. Failed experiments leave FTS configuration and the last
accepted artifact unchanged.
