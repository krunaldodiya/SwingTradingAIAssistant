# Persistent-Memory Improvement PRD Suite

Status: **future product/specification authority; implementation not started**
Delivery type: documentation only
Repository baseline: `b5e03593310e96bc73ab4ef65c385dec08c75ebc`
Audited persistent-memory baseline: `79d07ccc41d483076bd1ee9acc4b876dec6eae54`

This suite records the accepted product direction and experiment gates for future
versions of the local persistent-memory product. The current v0.1 implementation
is Prime Agent-coupled; the accepted future direction is a harness-neutral core
with first-class Prime Agent and Pi coding agent adapters over the same stores and
contracts. This does not claim universal zero-work compatibility. It does not
implement, authorize, or schedule a memory-tool change. This delivery changes no
memory source, schema, runtime dependency, database, service, migration bundle,
benchmark result, or operating policy. Every implementation slice requires
separate explicit promotion, strict TDD, review, and release evidence in the
memory-tool repository.

## Suite map and authority

| Document | Authority |
|---|---|
| [01 — benchmark](01-versioned-memory-benchmark-prd.md) | Dataset, sealed split, retrieval/downstream metrics, safety cases, artifacts, and gates |
| [02 — observability and evidence](02-observability-evidence-and-integrity-prd.md) | Capture/retrieval diagnostics, time vocabulary, deterministic evidence bundles, citation and duplicate audits |
| [03 — experiments](03-experiment-first-improvement-protocols.md) | FTS baseline and guarded semantic, bootstrap, graph, and consolidation experiments |
| [04 — safety and delivery](04-safety-migration-and-staged-delivery.md) | Privacy, isolation, security, dependencies, migration, staged acceptance, rollback, and decision log |
| [05 — reference lessons](05-reference-system-lessons.md) | System-specific findings, exact audited revisions, benchmark caveats, and ideas not to import |
| [06 — harness-neutral core and adapters](06-harness-neutral-core-and-adapter-contract-prd.md) | Neutral core boundary, first-class Prime/Pi V1 adapters, shared-store continuity, conformance, compatibility, and rollback |

Where the suite conflicts internally, the narrower contract owns its named
subject; safety invariants in Document 04 always win. Document 06 owns the closed
host-adapter boundary and does not relax Document 03's rejection of an arbitrary
plugin ecosystem or Document 04's local/no-network rules. Where this suite
conflicts with an implemented memory-tool contract, the implemented contract
remains current runtime authority until a separately approved versioned change
ships. Repository Markdown reviewed with code becomes authoritative only for the
future product behavior it explicitly promotes.

## Evidence hierarchy and audit seal

Recommendations use this order of evidence:

1. explicit owner direction and the completed independent audit decision;
2. executable behavior and tests at the exact persistent-memory revision;
3. source code and committed result artifacts at an exact reference revision;
4. first-party documentation at that revision, labeled as documentation rather
   than observed behavior;
5. independently reproduced aggregate calculations from committed artifacts;
6. conceptual media or vendor claims, which can suggest a question but cannot
   prove capability, quality, safety, or suitability.

The audit seal is:

| Subject | Exact identity |
|---|---|
| Prime persistent memory | `79d07ccc41d483076bd1ee9acc4b876dec6eae54` |
| Hindsight | `c43a3ebfabe34f1eb8da9207eb4ee94ec08bce1e` |
| Mnemosyne | `85a4b88b506252ac522285f35ff86792731c65f3` |
| MemPalace | `906b918a7c6ebb2a9198a6bf5a78f30a173fea56` |
| GBrain | `fb141969f59043005b911d149d8c7039d41aec35` |
| Video | YouTube `R1TNGOZAOZs`, Wanderloots, published 2026-08-07; transcript inspected |

Reference source paths in Document 05 are relative to these sealed repository
revisions. Reference repositories remain read-only idea sources. Their code is
not copied and their runtime is not adopted.

## Current baseline to preserve

The audited tool is a small local continuity layer, not an autonomous knowledge
engine:

- Python standard-library runtime with local SQLite/FTS5 lexical retrieval;
- no network, hosted service, embeddings, generative model, or background worker;
- `global.sqlite3` physically separate from one SHA-256-named database per
  canonical project;
- one explicit global, project, session, or bounded multi-project selection—no
  implicit global-plus-project or all-project union;
- unverified transcript evidence kept distinct from explicitly curated semantic
  records and versioned procedural skills/policies;
- explicit `remember`, `update`, invalidate, supersede, forget, import, export,
  and delete operations rather than automatic truth promotion;
- provenance, source time, confidence, audited revision, validity, lifecycle,
  branch warning, and source-pointer information where applicable;
- bounded pull-based recall and recent activity rather than automatic wake-up;
- checksummed plaintext migration bundles, collision refusal, project rebinding,
  atomic/collision-safe publication, and rebuildable derived FTS state;
- bounded redaction and secret refusal as defense in depth, never represented as
  encryption, DLP, backup, or secure erasure.

The 34 audited tests establish operational contracts, isolation, fault behavior,
concurrency, path defenses, migration, and packaging. They do **not** establish
retrieval usefulness, semantic recall quality, downstream continuity, or safe
abstention. Closing that evidence gap is the first accepted improvement.

Known residual boundaries remain explicit: plaintext local data, no secure erase,
advisory POSIX locks with weaker process-local Windows behavior, residual path
TOCTOU risk, no general durable crash journal spanning filesystem and registry
commits, and bounded append-oriented Prime JSONL assumptions. This PRD does not
silently claim those risks are fixed.

## Product principles

1. **Evidence is not truth.** Storage, retrieval rank, recency, frequency,
   importance, proof count, vector similarity, graph connectivity, and fluent
   prose do not establish correctness.
2. **Isolation precedes relevance.** Physical project selection and hard scope
   filters run before any lexical, semantic, graph, temporal, or bootstrap step.
3. **Abstention is successful behavior.** Missing, stale, out-of-window,
   conflicting, unsupported, or scope-forbidden evidence remains explicit.
4. **The tool supplies evidence; the consumer reasons.** The deterministic
   memory layer may package and validate recalled evidence but does not generate
   opinions, persona, recommendations, or unsupported synthesis.
5. **No benchmark-driven production feature.** A feature must improve sealed
   held-out behavior, preserve safety, justify cost, and pass an explicit
   promotion decision. Vendor results are never substitution evidence.
6. **Indexes are derived.** Raw source semantics, curated records, provenance,
   scope, lifecycle, and migration identity remain authoritative; lexical,
   semantic, or graph indexes must be reproducible or disposable.
7. **No silent transformation or mutation.** Capture changes are reported;
   audit commands are read-only; consolidation produces proposals only unless a
   later explicit curated write is independently authorized.

## Accepted roadmap

The following are accepted as future specification work, not implementation in
this delivery:

1. a versioned privacy-safe benchmark for retrieval and downstream behavior;
2. capture and retrieval observability, including transformation/truncation and
   candidate/filter/rejection diagnostics;
3. a deterministic evidence-bundle contract with recalled-record citation
   allowlisting and explicit gaps/conflicts;
4. read-only citation/source-pointer integrity and exact-duplicate audits;
5. explicit timezone-aware UTC `since`/`before` filters and a dual-time
   vocabulary separating learned/source time from optional event-valid time; and
6. one neutral local core with closed, first-class Prime Agent and Pi Coding
   Agent V1 adapters sharing the configured store and exact project identity.

The following are experiment-first and may not enter production until their
individual gates pass:

- a curated-only bounded bootstrap helper;
- local semantic candidate retrieval fused with FTS by reciprocal rank fusion;
- exact-ID, typed, project-local edges in a disposable SQLite store;
- proposal-only consolidation with exact supporting evidence and zero automatic
  writes.

## Global non-goals

This suite does not approve wholesale adoption of any reference runtime; hosted
or remote memory; a public generic CLI, server, MCP, sync, or multi-machine
writer; arbitrary/dynamic host plugins; broker, market, or trading integration;
persona or mental-model generation; raw transcript wake-up; background
reflection; autonomous truth promotion; fuzzy entity resolution; semantic
deduplication; citation rewriting; or an unreviewed runtime dependency. The two
closed adapters accepted in Document 06 are future specifications, not current
Pi support or a general plugin exception.
It does not modify the SwingTradingAIAssistant research pipeline, roadmap,
market-regime contracts, sprints, or market logic.

## Promotion rule

A future implementer must name exactly one PR-sized slice from Document 04,
revalidate the audited memory-tool baseline and applicable external evidence,
write focused failing tests first, preserve every invariant above, and publish
sealed command/result evidence. No later document, issue state, benchmark score,
or convenience request implicitly promotes implementation.
