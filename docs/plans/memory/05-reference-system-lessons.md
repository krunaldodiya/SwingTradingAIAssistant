# Reference-System Lessons and Audit Caveats

Status: **sealed comparative-audit record; no implementation authority**
Depends on: [suite evidence hierarchy](README.md) and
[experiment gates](03-experiment-first-improvement-protocols.md), plus the
[harness-neutral adapter boundary](06-harness-neutral-core-and-adapter-contract-prd.md)

## Purpose and scope

This document preserves system-specific lessons from the completed independent
audit without importing a reference runtime or treating vendor documentation and
benchmark scores as proof for Prime. It records questions worth testing, unsafe
patterns to avoid, and the exact revisions to revalidate if future implementation
is promoted.

Reference repositories were read-only idea sources. No code was copied. This
suite does not add a dependency, clone, service, model, schema, database, runtime
integration, or network path. Source paths, when mentioned (for example
`README.md`), are relative to the sealed revision and identify the kind of
evidence inspected; documentation claims remain lower in the evidence hierarchy
than executable behavior and committed raw artifacts.

## Audit seal

| Subject | Exact audited identity | Role in this suite |
|---|---|---|
| Prime persistent memory | `79d07ccc41d483076bd1ee9acc4b876dec6eae54` | current behavioral baseline |
| Hindsight | `c43a3ebfabe34f1eb8da9207eb4ee94ec08bce1e` | recall/association/reflection reference |
| Mnemosyne | `85a4b88b506252ac522285f35ff86792731c65f3` | local capture/retrieval/consolidation reference |
| MemPalace | `906b918a7c6ebb2a9198a6bf5a78f30a173fea56` | benchmark and hybrid-retrieval reference |
| GBrain | `fb141969f59043005b911d149d8c7039d41aec35` | session-memory/bootstrap reference |
| Video | YouTube `R1TNGOZAOZs`, Wanderloots, published 2026-08-07 | conceptual media only; transcript inspected |

The seal is an identity, not an endorsement or freshness promise. A future slice
must confirm that the referenced revision and any applicable upstream evidence
are still available, unmodified, properly licensed, and relevant. Later branch
behavior cannot be silently attributed to these revisions.

## Audit method and claim discipline

The audit separated:

1. observed executable/source behavior at an exact revision;
2. committed tests and result artifacts at that revision;
3. independently reproduced aggregate calculations from those artifacts;
4. first-party `README.md` or other documentation claims; and
5. conceptual/video claims that merely suggest an experiment.

A feature name shared by two systems does not establish equivalent semantics.
“Memory,” “reflection,” “graph,” “hybrid,” “temporal,” “confidence,” and
“benchmark accuracy” were treated as system-local vocabulary until verified.
Missing negative tests, absent threat models, incomplete packaging evidence, and
unclear dataset denominators remain caveats rather than being filled by inference.

## Prime baseline: preserve before extending

At `79d07ccc41d483076bd1ee9acc4b876dec6eae54`, Prime is a local stdlib-only
SQLite/FTS5 continuity layer with explicit physical database selection,
distinct transcript evidence and curated semantics, explicit lifecycle/write
operations, provenance, bounded pull recall, and checksummed migration bundles.
Its 34 audited tests cover operational contracts, isolation, faults, concurrency,
path defenses, migration, and packaging.

That suite does not measure useful recall, vocabulary mismatch, downstream
continuity, citation behavior, or safe abstention. The accepted lesson is to add
the sealed benchmark and observability before architecture. The small baseline is
also a control: any new mechanism must justify every additional dependency,
latency, storage byte, migration, and attack surface.

## Hindsight

Sealed revision: `c43a3ebfabe34f1eb8da9207eb4ee94ec08bce1e`.

### Useful lessons

Hindsight demonstrates a broader retain/recall/reflect framing, multiple memory
representations, semantic and relational retrieval concepts, temporal or
historical context, and higher-level synthesized views. The audit treated those
as evidence that memory quality has separate capture, retrieval, and reasoning
questions—not as a package to embed.

Ideas adopted at specification level:

- evaluate retrieval and downstream behavior separately;
- expose learned/source time separately from event-valid and system transaction
  time;
- make candidate streams and relationships observable;
- preserve explicit gaps/conflicts instead of presenting one fluent memory; and
- test whether contextual association helps only after physical scope filtering.

Ideas admitted only as experiments:

- a local semantic candidate stream fused with FTS;
- exact-ID typed relationships in a disposable project-local store; and
- proposal-only consolidation with exact supporting evidence.

### Caveats and non-imports

Hindsight's architectural breadth, service/runtime assumptions, generated or
higher-level memory representations, mental-model behavior, and automatic
retain/reflect workflows do not match Prime's small local explicit-write trust
boundary. Its own terminology and any claims in `README.md` cannot prove Prime
benchmark gain, project isolation, offline packaging, deterministic migration,
or prompt-poisoning resistance.

Wholesale runtime adoption, hosted/remote memory, mental models/persona,
automatic reflection, model-authored truth, and background writes are rejected or
deferred by Documents 03 and 04. A graph or semantic score can suggest relevance
but can never establish truth.

## Mnemosyne

Sealed revision: `85a4b88b506252ac522285f35ff86792731c65f3`.

### Useful lessons

Mnemosyne illustrates an agent-local memory workflow spanning capture, search,
organization, session continuity, and maintenance. The audit found value in
examining capture transformations and losses rather than reporting only a
successful sync, and in distinguishing exact/lexical retrieval from broader
semantic recall.

Ideas adopted at specification level:

- capture observations for selection, normalization, redaction, truncation, and
  exclusion without retaining the removed secret-bearing text;
- retrieval pipeline counts and closed rejection reasons;
- read-only integrity and exact-duplicate audits; and
- explicit maintenance visibility instead of silent mutation.

Ideas admitted only as experiments are a curated-only bounded bootstrap and a
proposal-only consolidation result. Both are pull/caller initiated and preserve
exact supporting IDs, conflicts, gaps, and zero automatic writes.

### Caveats and non-imports

Hook-driven capture, embedding/hybrid components, decay or salience policies,
maintenance processes, and consolidation behaviors are system-specific. Their
presence or description in `README.md` does not establish privacy, deterministic
rebuilds, citation integrity, cross-project isolation, benchmark improvement, or
safe failure in Prime.

Prime will not import a plugin/hook ecosystem, wake on raw transcript data, use
recency/importance as truth, perform destructive deduplication, resolve entities
fuzzily, or let a background model mutate durable memory. Embeddings and
reranking remain deferred until the benchmark exposes a measured need and the
local RRF experiment passes.

## MemPalace

Sealed revision: `906b918a7c6ebb2a9198a6bf5a78f30a173fea56`.

### Committed-result facts and reproduced comparison

The audited committed results report:

- raw total: **483/500 = 96.60%**, with a two-sided 95% Wilson interval of
  **94.62%–97.87%**;
- hybrid total: **443/450 = 98.44%**, with a two-sided 95% Wilson interval of
  **96.82%–99.24%**; and
- on the **same 450-case paired subset**, raw **435/450 = 96.67%** versus hybrid
  **443/450 = 98.44%**.

Independent recomputation of the paired rows found **12 rescues** (raw wrong,
hybrid correct) and **4 regressions** (raw correct, hybrid wrong), a net gain of
8/450 or **+1.78 percentage points**. The two-sided exact McNemar/binomial paired
test is approximately **`p=0.0768`**.

A separate committed category-result file is stale or inconsistent with the
benchmark prose: for the user, preference, and assistant categories respectively,
the file reports **91.4% / 96.7% / 96.4%**, while the prose reports
**95.7% / 93.3% / 92.9%**. The audit did not silently choose either series.
Any reuse must identify the exact artifact, recompute category numerators and
denominators from per-case rows, and resolve or explicitly preserve the
mismatch.

These figures must stay together. Comparing 483/500 directly with 443/450 mixes
denominators, and the unpaired Wilson intervals do not replace the paired
analysis. The paired gain is suggestive but does not meet a conventional 0.05
threshold, contains real regressions, and does not demonstrate Prime's
isolation, temporal, abstention, poisoning, provenance, citation, resource, or
downstream-continuity requirements.

### Useful lessons

MemPalace's most useful contribution is methodological: preserve per-case raw
outcomes, compare candidates on identical case IDs, count rescues and
regressions, publish category behavior rather than one total, and independently
recompute aggregate/statistical claims. It also motivates testing hybrid
retrieval as a rank-fusion experiment rather than assuming semantic retrieval is
better.

Accordingly Document 01 requires paired comparisons, confidence intervals and an
exact paired test, immutable artifacts, invalid-call accounting, and a spent
held-out split. Document 03 freezes FTS and semantic streams, uses deterministic
RRF, and demands a confirmation set plus safety/resource gates.

### Caveats and non-imports

The committed scores are evidence about the sealed MemPalace artifact and its
case definitions, not a transferrable product benchmark. Dataset selection,
case exclusions, prompt/model/judge configuration, denominator changes, and
category composition determine what the numbers mean. High aggregate accuracy
does not show abstention quality or absence of forbidden-scope hits.

No MemPalace implementation, benchmark label, corpus, answer aid, evaluator, or
runtime is copied. A Prime experiment must use privacy-reviewed synthetic data,
its own sealed case families, the unchanged FTS comparator, and per-case safety
labels.

## GBrain

Sealed revision: `fb141969f59043005b911d149d8c7039d41aec35`.

### Useful lessons

GBrain demonstrates the product appeal of durable session continuity, organized
memory layers, and making relevant prior context available near session start.
The audit used it to sharpen two separate questions: whether a consumer knows to
ask for memory, and whether a small bootstrap packet helps resume a verified
checkpoint.

Ideas adopted at specification level:

- explicit `know-to-ask` and continuity benchmark categories;
- a bounded evidence bundle rather than undelimited memory injection;
- citation/source-pointer integrity and checkpoint freshness checks; and
- observable no-write/write-back decisions after a correction or milestone.

The only proactive mechanism admitted for experiment is curated-only bounded
bootstrap from one explicitly selected database. It is a proposal, excludes raw
transcripts, preserves scope/lifecycle/conflicts, and is compared with no
bootstrap and ordinary pull.

### Caveats and non-imports

Session hooks, file/context injection, layered summaries, background maintenance,
or operational conventions described by GBrain or its `README.md` do not by
themselves prove isolation, provenance, safe prompt handling, deterministic
recovery, or improved Prime behavior. Convenience at session start also creates
an attention and injection cost.

Prime rejects raw wake-up, automatic prompt injection, background LLM/dream
writes, persona generation, and auto-curation. It does not adopt GBrain wholesale
or turn the SwingTradingAIAssistant repository into a memory runtime.

## Video `R1TNGOZAOZs`

The Wanderloots video, published 2026-08-07, was inspected through its transcript
as conceptual media. It discusses persistent agent memory, continuity, proactive
recall, reflection, or related system ideas. A transcript is not executable
behavior, source code, a threat model, a benchmark artifact, or proof that a
feature works safely.

The video contributes questions only: when should memory be pulled, how can a
session resume without flooding context, and how should repeated experience be
reviewed? The suite answers conservatively with know-to-ask cases, a bounded
curated bootstrap experiment, and proposal-only consolidation. It does not accept
persona/mental-model generation, raw transcript wake-up, autonomous reflection,
background dream writes, or guaranteed “learning.”

## Cross-system disposition matrix

| Concept | Disposition | Smallest Prime-specific action |
|---|---|---|
| usefulness and downstream benchmark | Accepted | synthetic sealed two-layer benchmark |
| capture/retrieval observability | Accepted | bounded counters, flags, reasons, hashes |
| evidence bundle/citation allowlist/gaps/conflicts | Accepted | deterministic bounded packaging only |
| citation/source and exact-duplicate audits | Accepted | one-scope read-only reports, zero writes |
| UTC filters and dual-time vocabulary | Accepted | learned/source `[since,before)` first |
| curated bootstrap | Experiment | one selected DB, curated-only bounded proposal |
| semantic plus FTS | Experiment | local pinned encoder and deterministic RRF |
| typed relations | Experiment | exact IDs in disposable project-local SQLite |
| consolidation | Experiment | proposal only with exact cited support |
| embeddings/rerank/graph backend/plugins | Deferred | require measured failure and separate gate |
| server/MCP/sync/multi-machine memory | Deferred | no present product need or trust case |
| mental models/persona/reflection | Deferred or rejected | keep consumer reasoning out of tool |
| wholesale reference adoption | Rejected | independently specify the smallest behavior |
| auto truth/raw wake/background writes | Rejected | explicit pull and explicit curated mutation |
| fuzzy entities/metadata-only isolation | Rejected | exact IDs and physical DB selection |
| destructive dedup/citation rewrite | Rejected | read-only report and exact allowlist validation |

## Revalidation trigger

A future implementer revalidates only the reference material applicable to the
single promoted slice. It records the new observed SHA, license, source/test/result
paths, claim type, changed behavior, and whether this sealed lesson still holds.
A moved branch, changed README, newer score, or new vendor claim does not rewrite
this audit. Any correction is a new decision-log entry that supersedes the prior
claim and preserves the original seal.

The final decision remains: improve Prime from its own measured failures, preserve
its small local safety boundary, and treat every reference mechanism as a
hypothesis rather than inherited authority.
