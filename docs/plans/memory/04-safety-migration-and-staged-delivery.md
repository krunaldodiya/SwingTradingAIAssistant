# Safety, Migration, and Staged Delivery PRD

Status: **future delivery authority; no implementation in this delivery**
Applies to every contract and experiment in this suite, including the closed
Prime/Pi host-adapter work in
[Document 06](06-harness-neutral-core-and-adapter-contract-prd.md). When another document
conflicts with this one, this document's safety invariant wins.

## Purpose and decision

Memory changes can expose private text, join isolated projects, corrupt durable
records, create dependency/network behavior, or silently turn an experiment into
production. Delivery is therefore a sequence of independently reversible,
PR-sized slices with explicit evidence and no implicit promotion.

- Expected value: preserve the audited trust boundary while allowing measured,
  reviewable improvements.
- Scope fit: safety and release controls for the local project-agnostic memory
  tool only.
- Material risk: schema/data loss, isolation regression, plaintext leakage,
  poisoned evidence, supply-chain expansion, and unrecoverable partial commits.
- Smallest alternative: keep the exact audited implementation unchanged.
- Decision: **accepted as a mandatory gate for future work**. This documentation
  delivery performs no migration, dependency, source, database, or policy change.

## Non-negotiable safety invariants

1. **Physical isolation before relevance.** `global.sqlite3` remains separate
   from one SHA-256-named database per canonical project. One call selects one
   explicit global, project, session, or bounded explicit project set. There is
   no implicit global-plus-project or scan-all fallback.
2. **Evidence is not truth.** Transcript evidence remains unverified. Rank,
   vector similarity, recency, frequency, importance, proof count, edge count,
   citations, and fluent text do not elevate truth status.
3. **Explicit mutation only.** Durable create, update, invalidate, supersede,
   forget, delete, import, and migration actions remain caller-authorized and
   auditable. Recall, audit, bootstrap, and consolidation-proposal paths have no
   write capability.
4. **Provenance survives.** Record/source identities, source time, scope,
   lifecycle, audited revision, validity, confidence where explicit, branch
   warnings, and migration identity cannot be dropped to satisfy a new index.
5. **Indexes are derived.** FTS, vectors, graphs, caches, and summaries are
   rebuildable/disposable. Raw authoritative records and explicit curated
   semantics remain the source of record.
6. **Abstention is valid.** Missing, stale, conflicting, out-of-window,
   unverified, truncated, and unavailable states are never repaired by guessing.
7. **Local and pull-based.** The accepted production path has no hosted service,
   network request, background worker, model call, wake-up loop, or telemetry.
8. **Untrusted content stays data.** Stored prompt-like text cannot change
   policy, call tools, broaden scope, forge citations, or authorize a write.

A release that violates any invariant is rejected even if all usefulness metrics
improve.

## Privacy and data classification

Memory databases and exports are plaintext local artifacts and must continue to
be described that way. Redaction and secret refusal are bounded defense in depth,
not encryption, anonymization, DLP, backup, access control, secure erase, or legal
retention compliance. Documentation and UI must not imply otherwise.

The default privacy posture is data minimization:

- store only eligible visible user/assistant text after declared transformations;
- never retain hidden reasoning, tool payloads, image bytes, removed parts,
  pre-redaction values, regex matches, credentials, tokens, or environment dumps;
- diagnostics use hashes, counts, closed reasons, and sanitized pointers;
- public CI/benchmarks contain synthetic data only;
- live databases, raw transcripts, migration bundles, and private exports never
  become fixtures, support attachments, or committed artifacts; and
- temporary copied roots use restrictive permissions and deterministic cleanup.

A later sanitized-corpus evaluation requires a separate data inventory, license
and privacy review, reviewer identity, deletion plan, and proof that reversible
identifiers and secrets are absent. Uncertainty means exclusion.

## Isolation and authorization matrix

Every public operation declares its admitted database selection and mutation
capability:

| Operation | Selection | Writes authoritative memory? |
|---|---|---|
| recall/trace/evidence bundle | one explicit scope or explicit bounded project set | No |
| integrity/duplicate audit | one explicit physical DB or copied bundle | No |
| curated bootstrap proposal | one explicit global or project DB | No |
| semantic/edge/consolidation experiment | disposable copy of one explicit DB | No |
| curated remember/update/lifecycle action | one explicit global or project DB | Yes, explicit |
| import/migration | one explicitly bound destination under collision rules | Yes, explicit |
| delete/forget | exact selected record/scope/root with confirmation contract | Yes, explicit |

Metadata scope filters never substitute for physical selection. Diagnostic counts
for unselected databases are also forbidden because existence is sensitive.
Canonical project identity and SHA-256 database naming are validated before path
construction. Existing containment, symlink/no-follow, regular-file, ownership,
permissions, advisory lock, collision, and atomic-publication defenses must be
retested for every filesystem change.

Windows process-local locking limitations, POSIX advisory locks, residual path
TOCTOU risk, plaintext files, and lack of secure erase remain known limitations
until separately solved. A feature may not relabel them as closed.

## Provenance and lifecycle preservation

A schema or transform is lossless only when it preserves exact content bytes or a
specified canonical equivalent and all applicable metadata: record ID, database
identity, project binding, scope/session, kind/evidence type/truth status,
source pointer and content hash, source/learned time, optional event-valid time,
created/updated transaction time, explicit confidence, audited SHA, validity,
expiry, invalidation/supersession links, branch/rewrite warning, transformation
flags, and original migration identity.

Unknown enum values, malformed timestamps, dangling lifecycle links, hash
mismatch, or unsupported newer schema fail closed. They are quarantined or
reported; they are not coerced to an active default. Migration does not decide
which conflicting record is true. Round trips must preserve unknown-but-bounded
extension payloads only when the version contract explicitly permits them;
otherwise import refuses the bundle.

## Security and poisoning review

Threat cases include secret capture, path traversal/symlink swap, malicious
SQLite or bundle input, checksum substitution, zip/archive expansion, resource
exhaustion, SQL/FTS query injection, prompt injection in content, citation
forgery, foreign-project ID probing, model-file substitution, dependency
confusion, runtime download, telemetry, and a crash between filesystem and
registry publication.

Required controls are bounded input sizes/counts/depths; parameterized database
operations; canonical path containment and no-follow admission; exact digest and
manifest verification; collision refusal; atomic file publication; lock/timeout
behavior; closed enums; deterministic parsing; sanitized exceptions; scope-first
candidate construction; citation allowlists; write traps on read-only commands;
network traps; and fail-closed model/index identity.

No memory content is executable configuration. URLs, shell text, tool names,
model instructions, and write requests inside a record are quoted as data.
Renderers visibly delimit evidence and expose kind, scope, lifecycle, source, and
unverified status. Benchmark poisoning canaries must demonstrate zero network,
tool, scope expansion, citation forgery, policy override, and write side effects.

## Dependency and no-network policy

The production baseline remains Python standard library plus SQLite/FTS5. An
accepted documentation or benchmark slice adds no runtime dependency. A future
candidate needing a package, native library, encoder, or model must produce a
separate dependency decision containing exact package/model/version/checksum,
license, transitive inventory, supported platforms, wheel/build behavior,
security scan, size/startup/resource cost, update policy, reproducible install,
and removal plan.

Experimental dependencies live only in an explicit optional group and disposable
environment. Runtime download, version discovery, remote inference, telemetry,
package self-update, and network fallback are forbidden. Tests install/run with a
network trap. Missing optional state fails closed or selects the already accepted
FTS path; it never changes behavior by reaching the Internet.

## Versioned migration contract

Any durable schema or serialization change defines a new version and a canonical
migration plan before code. In-place mutation of the only copy is forbidden.

### Preflight

A migration must:

1. select one exact global/project database and acquire the applicable lock;
2. reject dirty/unsupported source versions, symlinks, non-regular files,
   containment failures, active writers, insufficient disk, and invalid perms;
3. compute source database, registry, and manifest hashes plus row/count/schema
   inventory; run SQLite integrity and foreign/lifecycle checks;
4. bind tool code SHA, source contract, destination contract, project identity,
   evaluation time, configuration, and migration ID; and
5. create a verified backup or checksummed export in a caller-selected safe
   location without claiming it is encrypted.

Preflight is read-only. Failure produces a sanitized report and zero destination
publication.

### Copy, validate, publish

Migration writes a new temporary database in the same destination filesystem,
uses explicit transactions, copies authoritative rows before rebuilding derived
indexes, and never follows input paths from stored content. Validation compares
row identities, canonical content hashes, complete provenance/lifecycle fields,
expected transformations, schema/version, FTS/index rebuild membership, SQLite
integrity, and deterministic bundle/report hashes.

Publication is atomic and collision-safe: fsync data and directory as supported,
refuse an existing unexpected destination, rename only the fully validated file,
and update any registry/manifest with an explicitly recoverable order. Because a
general cross-filesystem/registry crash journal is not currently promised, the
slice must either remain inside the existing proven atomic boundary or add and
test a narrowly specified recovery journal before claiming crash safety.

### Compatibility, round trip, and rebind

The contract declares reader/writer compatibility and whether downgrade is
lossless. Export/import round trips reproduce authoritative canonical rows and
checksums; derived indexes may rebuild. Project rebinding requires an explicit
source and destination canonical project identity and preserves the original
binding in migration provenance. A collision, mismatched binding, newer unknown
version, missing manifest member, or checksum mismatch refuses the entire import.
Partial best-effort import is forbidden for official migration.

## Rollback and recovery

Until post-publication verification succeeds, the old database remains intact
and authoritative. Rollback removes/quarantines only the new untrusted temporary
or published candidate, restores the previous registry pointer when applicable,
and reopens the old database read-only before resuming writes. It never attempts
to reverse-engineer old rows from a lossy destination.

Crash/fault tests inject failure before and after every durable write, fsync,
rename, registry change, and cleanup. Recovery must converge to exactly one
recognized authoritative version, never a silent union. Ambiguous state blocks
writes and emits a repair plan. A successful rollback report binds hashes for the
preserved old database and all quarantined artifacts.

A release has an explicit rollback trigger: safety invariant failure, integrity
mismatch, unexpected network, dependency/model mismatch, material benchmark
regression, unrecoverable latency/resource excess, or any post-release corruption
signal. Rollback returns to the last accepted contract/configuration; published
evidence is superseded, never edited in place.

## Staged PR-sized delivery

No issue state or roadmap line starts implementation automatically. The owner
must explicitly promote exactly one slice below. Every slice starts from a fresh
revalidation of the memory-tool baseline and uses strict failing-test-first TDD.

1. **Benchmark manifest and synthetic fixtures** — no live memory input.
2. **Pure-retrieval evaluator and sealed baseline report** — no retriever change.
3. **Capture observation contract** — counters/flags only, no new raw retention.
4. **Retrieval trace** — bounded diagnostics with foreign-scope side-channel
   tests.
5. **Learned/source-time UTC filters** — `[since,before)` only; no event-time
   inference.
6. **Deterministic evidence bundle and citation allowlist** — packaging only, no
   answer generation.
7. **Read-only integrity audit** — zero writes under traps.
8. **Read-only exact-duplicate audit** — reporting only, no merge/delete.
9. **Curated bootstrap experiment** — disposable harness, no production default.
10. **Local semantic plus FTS/RRF experiment** — optional dependency/index only.
11. **Exact-ID typed-edge experiment** — disposable project-local edge store.
12. **Proposal-only consolidation experiment** — write API unavailable.
13. **Event-valid-time contract**, only after an authoritative use case and
    migration proposal exist.
14. **A separately promoted production candidate**, only after confirmation
    evidence and a dependency/migration/security decision.

A PR may narrow a slice; it may not bundle later slices for convenience. The
adapter stages in Document 06 are additional future slices under this same owner
promotion and checklist; they do not start automatically and cannot be bundled
into the slices above. Docs, contract, implementation, migration, release
evidence, and rollback mechanics must stay reviewable. Reference code is never
copy-pasted.

## Slice acceptance checklist

Every promoted slice must publish:

- [ ] owner promotion and named PR-sized slice;
- [ ] exact clean baseline SHA and audited-reference freshness statement;
- [ ] five-line candidate decision when a new module/source/factor applies;
- [ ] focused tests observed failing first, then passing;
- [ ] legacy memory-tool suite and packaging checks passing;
- [ ] synthetic safety tests for isolation, lifecycle, abstention, poisoning,
      citations, secrets, paths, collisions, concurrency, and fault points as
      applicable;
- [ ] for every prompt canary, a unique case/canary ID and payload hash, exact
      allowed quotation locations, the complete forbidden-sink set, and trace
      assertions proving zero canary-caused tool, network, write, scope, citation,
      policy, or task-control effects;
- [ ] atomic scenario-family split assignment and exact per-case/per-assertion
      reconciliation, including denied attempts, errors, and missing traces;
- [ ] sealed benchmark/config/per-case artifacts when behavior can change;
- [ ] zero unexpected network attempts and complete dependency inventory;
- [ ] privacy/provenance/security review and no private committed artifacts;
- [ ] forward migration, compatibility, fault injection, and rollback evidence
      for every durable change;
- [ ] resource/latency/context budgets and platform limitations;
- [ ] independent review of the exact candidate SHA;
- [ ] explicit decision-log entry; and
- [ ] clean diff proving no unrelated SwingTradingAIAssistant market, roadmap,
      sprint, or research-pipeline change.

A checkbox without its named artifact is not evidence.

## Decision log

Future decisions append immutable entries; corrections supersede earlier entries.

```text
MemoryImprovementDecisionV1 {
  decision_id: stable ID
  decided_at: UTC instant
  subject: exact contract/experiment/slice
  baseline_code_sha: SHA-40
  candidate_code_sha: SHA-40 or null
  dataset_and_artifact_sha256: ordered map
  evidence_summary: bounded text with per-category results
  invariant_results: closed map
  privacy_security_dependency_migration_reviews: ordered IDs
  known_limitations: ordered strings
  reviewers: ordered identities
  decision: ACCEPT_SPEC | PROMOTE_EXPERIMENT | PROMOTE_PRODUCTION |
            REVISE | DEFER | REJECT | ROLLBACK
  supersedes_decision_id: stable ID or null
  rollback_target: contract/config/artifact identity or null
}
```

Current entry: this suite is `ACCEPT_SPEC`. All implementation candidates are
unpromoted. The accepted current runtime remains the audited FTS tool until a
later exact decision says otherwise.
