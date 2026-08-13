# Harness-Neutral Core and Adapter Contract PRD

Status: **accepted future specification; no implementation in this delivery**
Proposed contracts: `memory-core@v1`, `memory-adapter-spi@v1`,
`memory-visible-transcript-event@v1`, `memory-source-checkpoint@v1`,
`memory-capture-authorization@v1`, `memory-adapter-manifest@v1`, and
`memory-adapter-conformance@v1`
Depends on: [suite authority](README.md),
[observability and evidence](02-observability-evidence-and-integrity-prd.md), and
[safety and delivery](04-safety-migration-and-staged-delivery.md)

## Purpose and owner decision

The audited v0.1 tool has a sound local storage and evidence boundary, but its
public package description, default directories, transcript discovery, JSONL
parser, identifiers, and skill-facing dispatcher are coupled to Prime Agent. The
next version must make the memory domain independent of a coding-agent harness
while keeping harness-specific capture and tool integration in small, versioned
adapters.

- Expected value: let Prime Agent and Pi coding agent use the same physically
  isolated memory stores and domain contracts without duplicating or translating
  curated truth.
- Scope fit: a local harness-neutral memory core plus two first-class coding-agent
  adapters; it does not change the SwingTradingAIAssistant research pipeline.
- Material risk: a generic adapter layer can blur identity, ingest hidden/tool
  data, load untrusted code, bypass authorization, or join isolated projects.
- Smallest alternative: extract only the current Prime parser behind a closed SPI,
  then add one independently conforming Pi adapter over the unchanged core.
- Decision: **accepted as a future module specification**; Prime Agent and Pi are
  both mandatory v1 adapters, and this PR authorizes Markdown only.

This is not a claim of zero-work universal compatibility. A new harness is
supported only after someone implements its adapter, freezes its format mapping,
and passes the complete conformance and release gates. In particular, the
current package does **not** support Pi Coding Agent. The existing v0.1 skill
remains unchanged and authoritative until a separately promoted implementation
ships.

## Local evidence and freshness boundary

This design used read-only inspection of the persistent-memory source, tests,
skill documentation, and package metadata at the audited revision. For Pi, it
used the locally installed `pi --version` and `pi --help`, package
`@earendil-works/pi-coding-agent@0.84.1`, and its packaged `sessions.md`,
`session-format.md`, `extensions.md`, `packages.md`, `settings.md`, `security.md`,
`sdk.md`, `rpc.md`, and `json.md`. No external tool, Pi setting, extension,
package, session, or memory store was modified.

Pi's packaged documentation describes JSONL tree sessions, extension/session
APIs, configurable session roots, and extensions that execute with the user's
full permissions. Those statements are specification inputs, not executable
memory evidence or a support claim. Before any implementation, the exact Pi
package, TypeScript declarations, fixture bytes, package license, and applicable
runtime behavior must be pinned and revalidated. A later upstream version or
similar JSON shape cannot inherit the `0.84.1` target row.

## Decision boundary and terminology

The **core** owns memory semantics, storage selection, authorization, indexing,
transactions, migration, and public domain results. An **adapter** owns only the
mapping between one declared harness contract and the core's versioned inbound
and outbound contracts. A **source** is one harness transcript stream or durable
session artifact. A **checkpoint** is adapter-specific capture progress for one
source; it is not a curated memory checkpoint. A **session key** is a core key
namespaced by adapter and harness session identity.

The target is practical portability, not a lowest-common-denominator parser:

- Prime-specific and Pi-specific fields stay in their adapters or bounded
  provenance extensions.
- The core never imports Prime or Pi packages and never branches on a harness
  name.
- An adapter cannot request a SQLite filename, choose an index, create a database
  connection, reinterpret lifecycle state, or call private core functions.
- Capability negotiation may reduce an optional diagnostic, but it may not
  weaken isolation, visible-text admission, provenance, or mutation controls.
- Missing required capability, unknown version, ambiguous identity, or stale
  checkpoint fails closed with a typed result; there is no best-effort fallback
  to another parser or storage root.

## Current v0.1 coupling to make explicit

At audited persistent-memory revision
`79d07ccc41d483076bd1ee9acc4b876dec6eae54`, the implementation is one Python
module with Prime-facing assumptions:

| Concern | Current v0.1 behavior | Portable v1 boundary |
|---|---|---|
| Memory root | `PERSISTENT_MEMORY_BASE_DIR`, otherwise `~/.prime/agent/memory` | `CoreConfigurationV1.storage_root`; neutral platform default, resolved before any adapter call |
| Session root | argument or `PERSISTENT_MEMORY_SESSION_ROOT`, otherwise `~/.prime/agent/sessions` | adapter configuration and discovery; never a core storage choice |
| Discovery | sorted immediate `*.jsonl` children of one root | `TranscriptAdapterV1.discover_sources()` with an explicit bounded source contract |
| Header | `type="session"` with `id` and canonicalizable `cwd` | adapter emits `SourceDescriptorV1` and a project-binding claim |
| Messages | `type="message"`; only `user`/`assistant` string or `type="text"` parts | adapter emits closed `VisibleTranscriptEventV1` values |
| Exclusions | thinking, tools, images, custom/control parts are skipped inside the Prime parser | exclusions are mandatory SPI invariants enforced again by the core |
| Progress | device/inode, size/mtime, byte offset, line number, and prefix hash | opaque adapter checkpoint plus core revision/CAS envelope |
| Rewrite | a non-resumable known file purges its prior rows and reparses | explicit `REPLACE_SOURCE` transaction with provenance and observation |
| Transcript identity | SHA-256 of absolute source filename, NUL, and entry ID | SHA-256 over adapter ID, source namespace/ID, revision, and event ID |
| Branch data | `parentId` is retained; branch state is bounded by available Prime evidence | normalized parent/event lineage and declared `ACTIVE`, `INACTIVE`, or `UNKNOWN` state |
| Public integration | async Python calls and the Prime skill dispatcher | harness-neutral async Python API plus separately packaged first-party adapters |

The table is a refactoring target, not authorization to move code. It also does
not claim that every Prime installation uses the default session root; an
explicit v0.1 override remains possible.

## Architecture and dependency direction

```text
Prime Agent runtime ---- PrimeAdapterV1 ----\
                                           \
                                            MemoryCoreV1 ---- isolated local stores
                                           /
Pi coding agent -------- PiAdapterV1 -------/

Initial approved surface: async Python library
Unapproved gated proposals: optional CLI -> optional MCP
                          (each requires separate owner promotion)
```

Dependencies point inward. Harness adapters may depend on the stable public core
package and their reviewed harness integration boundary. The core cannot depend
on adapters, harness SDKs, session directories, tool registries, RPC protocols,
or extension loaders.

The initial supported public surface is the async Python library. CLI and MCP are
unapproved gated proposals, not accepted surfaces or scheduled stages. Each
requires a separate owner promotion. Only after that promotion may a CLI be
specified as a separate local serialization and packaging slice; MCP additionally
requires its own authorization, protocol, poisoning, and transport decision and
cannot inherit CLI approval. Any approved MCP proposal may use local stdio and
must not make HTTP, a server, or network access mandatory. No HTTP API, daemon,
hosted service, telemetry, runtime download, or background watcher is required or
approved by this PRD.

If the reviewed Pi TypeScript integration and Python core cannot share a process,
a private bounded single-request bridge may carry only the canonical adapter
contracts. It uses exact argv without a shell, a pinned local interpreter and
package digest, closed canonical JSON over stdin/stdout, time and output bounds,
a minimal environment allowlist with no inherited secrets, no network, and no
long-running listener. It is adapter-internal—not a public CLI, RPC service,
daemon, or MCP implementation—and requires its own packaging/fault tests.

## Harness-neutral public domain API

### Configuration and caller context

```text
CoreConfigurationV1 {
  contract_version: "memory-core@v1"
  storage_root: absolute normalized path
  storage_layout_version: exact supported version
  lock_timeout_ms: bounded positive integer
  default_record_limit: bounded positive integer
  default_context_bytes: bounded positive integer
  redaction_configuration_sha256: SHA-256
  authorizer_id: configured trusted local authorizer
}

CallerContextV1 {
  caller_id: bounded non-secret identity
  adapter_id: exact registered adapter ID or "python-library"
  harness_instance_id: bounded local instance identity or null
  requested_scope: GLOBAL | PROJECT | SESSION | EXPLICIT_PROJECT_SET
  project_binding: ProjectBindingV1 or null
  session_key: SessionKeyV1 or null
  explicit_project_set: sorted bounded tuple[ProjectBindingV1]
  request_id: unique bounded ID
}
```

`storage_root` is selected once by the application/operator before adapter
construction. It is not accepted from transcript content, recalled records, tool
arguments containing arbitrary paths, or an adapter manifest. The core validates
containment, file type, ownership/permissions where supported, and layout before
opening a database.

`RootResolutionV1` is performed once by the core and its canonical root identity
is bound into caller, adapter-handshake, migration, and diagnostic artifacts. The
V1 precedence is: an explicit trusted `CoreConfigurationV1.storage_root`; a
future neutral `PERSISTENT_MEMORY_ROOT` environment value; a closed, secret-free
neutral user config file; then the frozen platform data default. The neutral
default does **not** live under `~/.prime` or `~/.pi`: expected candidates are
`$XDG_DATA_HOME/persistent-memory` or `~/.local/share/persistent-memory` on Linux,
`~/Library/Application Support/persistent-memory` on macOS, and the local
application-data directory on Windows. The implementation slice must freeze the
exact config location, fields, precedence, expansion, ownership, and platform
rules before code.

`PERSISTENT_MEMORY_BASE_DIR` and `~/.prime/agent/memory` are admitted only by the
explicit Prime legacy-compatibility profile described below. If neutral and
legacy sources resolve to different roots, the core refuses ambiguity instead of
searching, unioning, dual-writing, or creating a replacement empty store.
Relative paths, traversal, symlinks, unsafe ownership/permissions, unknown config
fields, commands, URLs, credentials, or memory content fail closed. No adapter
may select or override the core root.

### Operations

The public core exposes named async methods rather than a harness dispatcher:

```python
class MemoryCoreV1:
    async def capture(self, request: CaptureBatchV1) -> CaptureResultV1: ...
    async def recall(self, request: RecallRequestV1) -> RecallResultV1: ...
    async def recent(self, request: RecentRequestV1) -> RecentResultV1: ...
    async def remember(self, request: RememberRequestV1) -> CuratedRecordV1: ...
    async def update(self, request: UpdateRequestV1) -> CuratedRecordV1: ...
    async def invalidate(self, request: InvalidateRequestV1) -> CuratedRecordV1: ...
    async def forget(self, request: ForgetRequestV1) -> MutationResultV1: ...
    async def list_memories(self, request: ListRequestV1) -> ListResultV1: ...
    async def stats(self, request: StatsRequestV1) -> StatsResultV1: ...
    async def export_scope(self, request: ExportRequestV1) -> ExportResultV1: ...
    async def import_scope(self, request: ImportRequestV1) -> ImportResultV1: ...
    async def delete_project(
        self, request: DeleteProjectRequestV1
    ) -> MutationResultV1: ...
```

Every request includes `contract_version`, `CallerContextV1`, exact scope, bounded
inputs, and an idempotency/request identity where meaningful. Capture requires the
separate `CaptureAuthorizationV1` defined below; every other mutation includes
`MutationAuthorizationV1`. Results are closed, serializable domain values; no
result exposes a database connection, raw SQL, internal path, secret, or
executable callback. Recall remains bounded, pull-based, lexical by default, and
evidence-producing rather than answer-generating.

The curated kind, lifecycle, truth/evidence, time, provenance, bundle, citation,
gap, and conflict meanings remain those of Documents 02 and 04. A refactor may
version or rename their wire fields, but it may not coerce unknown values, weaken
physical selection, silently mix global and project data, or turn transcript
content into curated memory.

## Identity and physical isolation

### Project identity

```text
ProjectBindingV1 {
  binding_version: 1
  project_id: stable generated UUID
  canonical_project_path: normalized absolute path
  canonical_path_sha256: SHA-256 of canonical path bytes
  binding_state: ACTIVE | MOVED_PENDING_REBIND | REBOUND | INVALID
  original_binding_sha256: SHA-256 or null
  rebind_provenance_id: stable ID or null
}
```

Prime and Pi given the same canonical project path must resolve through the core
registry to the same `project_id` and physical project database. Harness folder
names, encoded session-directory names, display labels, Git remotes, repository
names, and transcript text cannot replace canonical binding. A worktree or moved
checkout is a distinct canonical path until the existing explicit rebind/import
contract validates the source identity, destination identity, collision rules,
and provenance.

An adapter supplies a claimed working directory from trusted harness metadata;
the core canonicalizes and resolves it. The adapter never supplies
`project_id`, a path hash, or a database filename as authority. A disagreement
between configured project path, harness metadata, and session header is a
closed `PROJECT_BINDING_MISMATCH`, not an invitation to index the source under
both projects.

### Global, project, and session

The neutral root retains separate physical global and project stores:
`global.sqlite3` is distinct from one SHA-256-named database per canonical
project binding. Exact layout is a core versioned concern. Global access is
always a separate explicit call. Bounded multi-project reads open only the exact
caller-authorized stores and never imply global access.

```text
SessionKeyV1 {
  adapter_id: exact adapter ID
  source_namespace: exact manifest namespace
  harness_instance_id: bounded identity
  external_session_id: bounded opaque identity
  canonical_session_sha256: SHA-256 of the preceding canonical tuple
}
```

Prime and Pi sessions are never equated merely because their external IDs or
names match. Project-scoped recall can return allowlisted evidence from both
adapters in the same project store, preserving each namespaced session and
source. Session-scoped recall selects one exact `SessionKeyV1`. An explicit
future session-rebind operation would require its own migration contract; fuzzy
or automatic cross-harness session merging is forbidden.

### Concurrent cross-harness use

Prime and Pi may read and write the same core project store concurrently only on
a released profile that proves the actual process topology. The core—not either
adapter—owns locks, SQLite WAL configuration, transaction boundaries, timeouts,
publication, and recovery. Writes to one project serialize; reads observe
committed transactions only.

V1 has a closed concurrency-profile enum:

| Profile | Permitted claim | Required behavior |
|---|---|---|
| `POSIX_ADVISORY_CROSS_PROCESS_V1` | Same-machine Prime, Pi, and mixed-process readers/writers on an exact supported local-filesystem/OS/Python/SQLite tuple | Cross-process lock exclusion, crash release, WAL/CAS, timeout, and fault tests must pass with independent processes before activation. Network filesystems and untested tuples refuse. |
| `WINDOWS_PROCESS_LOCAL_V1` | Multiple adapters/tasks inside one core process only | It cannot claim or activate mixed-process Prime+Pi, subprocess-core, or two-process safety. Any topology that can open the root from another process refuses before adapter activation. |
| `UNSUPPORTED_CONCURRENCY_V1` | No concurrent activation | Refuse activation and preserve the accepted store. |

No free-form or inferred profile is valid. A Windows or other process-local
implementation can graduate only under a separately versioned profile with proven
cross-process coordination; absence of observed contention, a process-local mutex,
or quiescing one adapter is not proof. The core validates the configured topology
against the profile before discovery/capture. An unsupported or ambiguous profile
returns `UNSUPPORTED_CONCURRENCY` without opening a writable store.

All lock-taking paths use this total order: (1) root registry, (2) global store if
involved, then (3) project stores in bytewise ascending
`physical_project_store_id` order; release is the exact reverse. Single-project
operations follow the same subsequence and may not bypass the registry. Migration,
export, import, rebind, delete, rollback, and WAL checkpoint are exclusive core
operations: they acquire the registry and every involved global/project store in
that order before validation/publication. No adapter-owned or operation-specific
lock may be acquired out of order, and no lock upgrade is allowed. Export takes a
consistent exclusive snapshot rather than racing publication; rebind/migration/
import/rollback stage privately and publish only while all required locks remain
held.

Every acquisition and SQLite busy wait shares one bounded operation deadline.
Expiry returns sanitized `BUSY`, rolls back the transaction, discards unpublished
staging, releases held locks in reverse, and leaves registry, rows, checkpoints,
root pointers, bundles, and lifecycle state unchanged. It never retries without a
lock or falls back to another root, an in-memory database, or partial publication.
Checkpoint publication, capture-authorization nonce consumption, and captured
rows are one transaction. Concurrent work on the same source uses expected
checkpoint/revision compare-and-swap: a stale writer receives
`CHECKPOINT_CONFLICT`, re-discovers, and retries within a bounded policy rather
than regressing progress. Different adapter namespaces cannot overwrite one
another even when source and entry IDs collide.

The documented POSIX advisory-lock, Windows process-local fallback, path TOCTOU,
plaintext, and crash-journal limitations remain explicit; only the first is a
cross-process release profile after the required proof. Session sources themselves
are read as bounded snapshots and never locked or modified; append races become
`IN_PROGRESS`, changed-snapshot retry, or rewrite handling.

## Versioned adapter SPI

### Adapter construction and discovery

```python
class TranscriptAdapterV1(Protocol):
    def manifest(self) -> AdapterManifestV1: ...
    async def probe(self, config: AdapterConfigurationV1) -> AdapterProbeV1: ...
    async def discover_sources(
        self, request: SourceDiscoveryRequestV1
    ) -> SourceDiscoveryResultV1: ...
    async def read_batch(self, request: SourceReadRequestV1) -> CaptureProposalV1: ...
    async def invoke(
        self, request: AdapterInvocationV1
    ) -> AdapterInvocationResultV1: ...
```

The application selects `adapter_id` from a compiled-in or explicitly constructed
trusted registry and passes inert validated configuration. Discovery means
capability and source discovery by that selected adapter; it never means scanning
Python entry points, import paths, npm packages, `~/.pi/agent/extensions`,
project extension folders, current directories, or transcript-supplied module
names. The core does not `eval`, dynamically import, or execute manifest content.

An integration may statically install reviewed first-party harness glue. For Pi,
a reviewed entry module may use the documented extension/SDK boundary only when
it is explicitly enabled and version-pinned; the memory product must not rely on
Pi's auto-discovered extension locations. Arbitrary third-party adapters and
runtime plugin ecosystems remain unsupported.

`AdapterConfigurationV1` contains only closed scalar/list/path settings bound to
a schema hash: source root, expected harness instance, explicit project path,
read limits, and enabled optional capabilities. It contains no credentials,
Python/JavaScript code, shell commands, URLs, database paths, storage layout,
callbacks, or import names.

### Capability and conformance manifest

```text
AdapterManifestV1 {
  contract_version: "memory-adapter-manifest@v1"
  adapter_spi_versions: sorted nonempty tuple
  adapter_id: reverse-DNS-style stable ID
  adapter_version: semantic version
  harness_id: stable product ID
  supported_harness_contracts: sorted closed ranges or exact revisions
  source_namespaces: sorted nonempty tuple
  transcript_format_versions: sorted tuple
  checkpoint_format_versions: sorted tuple
  event_envelope_versions: sorted tuple
  inbound_capabilities: sorted closed set
  outbound_capabilities: sorted closed set
  required_core_capabilities: sorted closed set
  configuration_schema_sha256: SHA-256
  limits: closed bounded map
  network_required: false
  automatic_prompt_injection: false
  automatic_curated_writes: false
  hidden_or_tool_capture: false
  filesystem_and_locking_profile: exact closed profile
  known_limitations: ordered strings
  conformance_fixture_version: exact version
  conformance_artifact_sha256: SHA-256 or null
}
```

Inbound capability values are
`DURABLE_SOURCE_DISCOVERY`, `INCREMENTAL_APPEND`, `SOURCE_REWRITE`,
`SOURCE_REMOVAL`, `STABLE_EVENT_ID`, `PARENT_LINEAGE`, `ACTIVE_BRANCH_STATE`,
`SOURCE_TIMESTAMP`, and `LIVE_EVENT_HINTS`. Outbound values are
`ASYNC_READ_CALLS`, `ASYNC_MUTATION_CALLS`, `EXPLICIT_MUTATION_CONFIRMATION`,
`STRUCTURED_RESULT`, and `CANCELLATION`.

Capability claims are not grants. The core intersects the manifest with its own
supported versions and the exact operation's requirements. Capture always
requires durable discovery, stable source identity, the visible-event envelope,
and checkpoint semantics. A required capability that is absent, contradictory,
or outside the support matrix returns `UNSUPPORTED_CAPABILITY` before storage or
tool action. `ACTIVE_BRANCH_STATE` may be optional only when every event is
explicitly labeled `UNKNOWN`; it may never be guessed. A future core or adapter
version is unsupported until its exact compatibility row and conformance artifact
exist.

A canonical manifest is UTF-8 JSON with sorted keys, compact separators, one
trailing newline, closed fields, and no environment-dependent absolute paths.
Duplicate adapter IDs/namespaces, overlapping ownership, unknown capabilities,
unbounded version ranges, a network/prompt/automatic-write claim, or an
unsupported locking profile fail installation/conformance. Capability claims are
never permission grants and manifests cannot come from memory or transcript
content.

## Inbound visible transcript event contract

### Source descriptor and event envelope

```text
SourceDescriptorV1 {
  adapter_id: exact manifest adapter ID
  source_namespace: exact manifest-owned namespace
  source_id: stable opaque bounded ID
  harness_instance_id: bounded identity
  external_session_id: bounded identity
  claimed_project_path: trusted harness metadata or null
  source_format_version: exact version
  source_revision: stable digest or generation identity
  source_pointer: bounded sanitized local pointer
}

VisibleTranscriptEventV1 {
  contract_version: "memory-visible-transcript-event@v1"
  source: SourceDescriptorV1
  event_id: stable source-local ID
  parent_event_id: stable source-local ID or null
  role: USER | ASSISTANT
  visible_text: bounded UTF-8 text
  source_timestamp: exact UTC instant or null
  branch_state: ACTIVE | INACTIVE | UNKNOWN
  sequence: nonnegative source-local order
  source_location: bounded line/byte/entry pointer or null
  content_sha256: SHA-256 of admitted visible text before core transformations
  adapter_extensions: closed bounded map or null
}
```

The event envelope is an admission request, not trusted truth. The core validates
manifest ownership of the namespace, project/session binding, ordering, duplicate
IDs, bounds, Unicode, timestamps, checkpoint relation, and content hash. It then
performs the declared normalization, secret redaction/refusal, truncation,
observation, and storage behavior. Raw pre-redaction text is held only for the
bounded call and is never logged or retained. Visible user/assistant text can
still contain pasted tool output, private data, or an unknown credential; built-in
and caller redaction are incomplete defense in depth. A redaction failure,
unsupported encoding, or ambiguity excludes the entry/source rather than storing
raw input. This is not encryption, DLP, secret detection, or secure erasure.

Only visible user and assistant text is eligible. The following are prohibited
as event text or extensions even if a harness serializes them next to messages:

- system/developer/control prompts and policy state;
- hidden thinking, chain-of-thought, reasoning summaries not visibly authored as
  an ordinary assistant message, or provider metadata;
- tool calls, tool arguments, tool results, command output, file diffs, logs, MCP
  payloads, extension state, usage/cost details, and environment dumps;
- credentials, API keys, tokens, cookies, authorization headers, private key
  material, or values matched by the core's secret policy;
- image/audio/video bytes, base64 content, embeddings, model caches, and arbitrary
  custom objects;
- Pi `custom`, `custom_message`, compaction/retained-tail, branch-summary, label,
  model/thinking-change, session-info, usage, and extension-owned text/state; and
- settings/config bodies, auth stores, context-file bodies, AGENTS/CLAUDE/SYSTEM
  files, skills, prompt templates, package state, telemetry IDs, provider
  requests/responses, and pre-redaction matches or discarded raw bytes.

An adapter must allowlist eligible fields rather than recursively collect strings.
The core repeats role/content validation so a defective adapter cannot downgrade
a prohibited part to an extension. Prompt-like text in `visible_text` remains
quoted untrusted evidence and cannot affect configuration, authorization, tool
selection, scopes, checkpoints, or citations.

Project/source paths, session IDs, timestamps, lineage, and adapter identities can
also be sensitive. Durable diagnostics use digests, counts, closed reasons, and
sanitized pointers by default. Databases, WAL/SHM, checkpoints, and bundles remain
plaintext local artifacts under Document 04's permission and residual-risk rules;
neither adapter transmits them over a network.

### Source namespace and identity collision rules

Each adapter owns at least one immutable namespace, for example a versioned Prime
local-JSONL namespace or a versioned Pi session-JSONL namespace. The final
transcript key includes `adapter_id`, namespace, harness instance, source ID,
source revision/generation where required, and event ID. Raw filenames and event
IDs alone are insufficient.

Fixtures deliberately reuse the same session UUID, entry ID, filename, content,
and timestamp across Prime, Pi, and two harness instances. Every row must remain
distinct unless it is an exact replay inside the same namespaced source revision.
Content similarity never deduplicates sources. A namespace rename is a migration,
not an adapter patch.

## Checkpoints, rewrites, removals, and branches

```text
SourceCheckpointV1 {
  contract_version: "memory-source-checkpoint@v1"
  adapter_id: exact adapter ID
  source_namespace: exact namespace
  source_id: exact source ID
  checkpoint_format_version: exact adapter-owned version
  source_revision: digest or generation identity
  opaque_position: bounded canonical JSON value
  observed_size_or_count: nonnegative integer or null
  verified_prefix_sha256: SHA-256 or null
  terminal_state: COMPLETE | IN_PROGRESS | REMOVED
  checkpoint_sha256: SHA-256
}

CaptureProposalV1 {
  contract_version: exact version
  caller: CallerContextV1
  source: SourceDescriptorV1
  expected_prior_checkpoint_sha256: SHA-256 or null
  disposition: APPEND | REPLACE_SOURCE | UNCHANGED | REMOVE_SOURCE | REFUSE
  events: ordered bounded tuple[VisibleTranscriptEventV1]
  next_checkpoint: SourceCheckpointV1
  discovery_snapshot_complete: boolean
  observations: bounded adapter diagnostics
}

CaptureAuthorizationV1 {
  contract_version: "memory-capture-authorization@v1"
  authorization_id: unique one-use nonce
  authorizer_id: exact configured trusted local authorizer
  issued_at: exact UTC instant
  expires_at: exact bounded UTC instant
  caller_context_sha256: SHA-256 of canonical CallerContextV1
  adapter_manifest_sha256: SHA-256 of the accepted canonical manifest
  adapter_id: exact accepted adapter ID
  source_namespace: exact manifest-owned namespace
  physical_storage_root_id: core-resolved root identity
  physical_project_store_id: core-resolved project-store identity
  physical_session_binding_sha256: SHA-256 of the project-store identity and exact
    SessionKeyV1, or null only for an explicitly project-scoped source
  disposition: exact proposed disposition
  expected_prior_checkpoint_sha256: exact proposed SHA-256 or null
  capture_batch_sha256: SHA-256 of canonical CaptureProposalV1
}

CaptureBatchV1 {
  contract_version: exact version
  proposal: CaptureProposalV1
  authorization: CaptureAuthorizationV1
}
```

The adapter may construct only `CaptureProposalV1`. After the complete immutable
proposal exists, the configured trusted local authorizer outside the adapter
canonicalizes it and issues `CaptureAuthorizationV1`; the adapter cannot mint,
copy, alter, broaden, refresh, or derive that authority from a manifest,
transcript, prompt, recalled record, model output, tool availability, or harness
configuration. `capture_batch_sha256` is the batch digest: it covers every
canonical proposal field, including caller, source, disposition, events, next
checkpoint, discovery completeness, and observations, while excluding only the
authorization object itself.

Before any row, checkpoint, nonce-use record, registry, or filesystem mutation,
the core recomputes the batch and caller digests and validates issuance, expiry,
one-use nonce, configured authorizer, accepted manifest digest, adapter and
namespace ownership, resolved storage root, physical project store, exact session
binding, disposition, and expected prior checkpoint. A mismatch or stale value
refuses the whole batch. Successful nonce consumption, captured rows, source
replacement/removal, and checkpoint publication occur in the same transaction;
there is no adapter-side authorization fallback or partial mutation.

Checkpoint payload semantics belong to the named adapter version; the core treats
`opaque_position` as bounded inert data and verifies its canonical digest. Prime
and Pi checkpoints are never exchanged or compared. The core binds a checkpoint
to its physical project store and exact namespaced source, then publishes it only
with the corresponding event transaction.

Rules are mandatory:

1. **Append:** allowed only when the adapter proves the prior revision/prefix and
   the core checkpoint matches. Duplicate replay is idempotent; changed prior
   content is not append.
2. **Incomplete EOF:** retain the last committed checkpoint and return
   `IN_PROGRESS`; do not consume an unterminated malformed unit that could become
   valid after append.
3. **Rewrite/truncate/rotation:** emit `REPLACE_SOURCE` with a new revision. The
   core atomically removes that source's old transcript rows and inserts the
   complete admitted replacement. It never touches curated records or another
   namespace and never describes replacement as consolidation.
4. **Removal:** emit `REMOVE_SOURCE` only from a complete, authoritative discovery
   snapshot. A permission error, partial scan, unsupported version, missing root,
   or budget stop is not removal. Removal is observed and transactional.
5. **Branch:** preserve parent lineage when available. Branch navigation that
   leaves old entries in the durable tree updates/derives branch state without
   deleting historical evidence. If the adapter cannot identify the active path,
   all affected rows are `UNKNOWN` and carry a branch warning.
6. **Branch rewrite:** changing parents, reusing an event ID with different
   content, or replacing a tree requires `REPLACE_SOURCE`; last-write-wins field
   updates are forbidden.
7. **Compaction/summary:** a harness-generated compaction or branch summary is not
   silently substituted for original visible turns. It is excluded in v1 unless
   a later evidence kind explicitly defines its visible provenance and benchmark.

Core observations reconcile sources considered/admitted/unchanged/replaced/
removed/refused; events offered/admitted/excluded/redacted/truncated; checkpoint
conflicts; branch states; and bounded closed reasons as required by Document 02.

## Required first-class adapters

### Prime Agent adapter

`PrimeAgentAdapterV1` is required for the v1 release and must reproduce the
current accepted behavior before adding capability. Its initial fixture contract
covers the audited v0.1 Prime JSONL assumptions listed above: session header,
message entries, stable entry/parent IDs where present, visible user/assistant
text only, UTC timestamp validation, bounded append handling, malformed/oversize
lines, rewrite replacement, and project-header mismatch refusal.

The adapter owns Prime source-root discovery and Prime parser evolution. The core
must not know `~/.prime`, Prime environment-variable names, JSONL field names, or
skill conventions. The adapter's outbound side maps the existing Prime skill/tool
experience to public async core requests and structured errors without changing
scope defaults or minting write authorization. Exact Prime harness revisions or
format versions supported at release must be pinned in the compatibility matrix;
“latest Prime” is not a range.

### Pi coding agent adapter

`PiCodingAgentAdapterV1` is equally required for the v1 release. Narrow local
research observed installed package `@earendil-works/pi-coding-agent` version
`0.84.1` and its shipped documentation; this is a specification input, not a
support claim or sealed reference-system endorsement. That observed contract has:

- sessions under `~/.pi/agent/sessions/`, organized by working directory, with
  documented resolution through `--session-dir`,
  `PI_CODING_AGENT_SESSION_DIR`, `sessionDir` settings, then the host default;
- JSONL session headers containing version, session ID, timestamp, and `cwd`;
- current session format v3 entries linked as a tree by `id`/`parentId`;
- `message` entries with user/assistant text plus separately typed thinking,
  tool-call, tool-result, image, custom, compaction, branch-summary, label, model,
  and session-info data; and
- documented session lifecycle/message/compaction/tree events plus an SDK and
  extension tool-registration boundary.

The Pi adapter must parse only the exact pinned session versions tested. For v3,
it maps the header `cwd` through the core project binder, uses header session ID
as a namespaced external ID, maps entry `id`/`parentId` and ISO timestamp, admits
only user string/text blocks and assistant `type="text"` blocks, and excludes all
other types listed above. It maps the durable tree to parent lineage and branch
state only when the pinned API/artifact supplies enough evidence; otherwise state
is `UNKNOWN`. Pi compaction `retainedTail`, compaction/branch summaries,
`custom_message`, and tool-result text are excluded in v1 rather than treated as
ordinary turns.

Pi source checkpoints are adapter-specific and must handle tree append, partial
EOF, in-place branch growth, rewrite/truncate, fork/new session files, and custom
session directories. Directory names encoded from a working path are discovery
hints only; the header and explicit caller project binding must agree. The
adapter cannot call Pi's list-all-sessions behavior as an implicit multi-project
memory request. It receives the already resolved root from trusted host context or
explicit adapter configuration; the core does not scrape arbitrary Pi settings,
search the home directory, install/update Pi, alter project trust, call `/share`,
export sessions, or contact package/model/version services.

Pi's own security documentation says extensions execute with full user
permissions and project trust is not a sandbox. The adapter therefore must be a
reviewed, version-pinned, explicitly enabled artifact; declining project-local
trust leaves it inactive without changing settings. A host trust decision does
not constitute curated-write authorization.

For outbound calls, a statically reviewed and explicitly enabled Pi integration
may map Pi tool calls or SDK calls to the public async core API. It must return
structured results, honor cancellation, display/obtain explicit mutation
confirmation, and never insert recalled text into a tool argument. It may use
supported Pi lifecycle events as bounded sync hints, but correctness must remain
pull-based and recover from missed/duplicate events by reconciling durable
sources. It must not auto-load arbitrary Pi extensions or require HTTP/network.

### Cross-harness continuity

Both adapters bind the same canonical checkout to the same core project database.
Therefore an explicit curated checkpoint written through Prime is available to a
later explicit Pi project recall, and the inverse is true, with the exact same
record ID, lifecycle, provenance, and content hash. Project recall may also
return unverified transcript evidence from both namespaces; results identify the
origin adapter/session and never pretend those sessions are one conversation.

Switching harnesses does not trigger automatic capture, bootstrap, global union,
write-back, or project rebind. The caller explicitly configures the project and
invokes sync/recall. A missing Pi capability or stale Prime checkpoint yields a
gap/refusal, not silent use of the other adapter's source checkpoint.

## Outbound async call and tool contract

```text
AdapterInvocationV1 {
  contract_version: exact version
  invocation_id: unique bounded ID
  caller: CallerContextV1
  operation: closed outbound public core operation; capture excluded
  arguments: exact operation request without credentials
  requested_capabilities: sorted closed set
  mutation_authorization: MutationAuthorizationV1 or null
  cancellation_deadline: UTC instant or null
}

AdapterInvocationResultV1 {
  invocation_id: exact input ID
  status: OK | REFUSED | UNSUPPORTED | CANCELLED | ERROR
  result_contract: exact public result version or null
  result: bounded structured value or null
  error: closed safe error or null
  observations: bounded safe counters
}
```

Adapters are translation layers, not agents. They do not formulate recall
queries from hidden context, choose scopes, synthesize answers, automatically
remember a result, or retry a refused mutation with broader authority. Async
acceptance and completion are distinct where the harness queues work; a tool
response cannot claim success until the core transaction commits.

Read requests require explicit caller context and scope. Non-capture durable
operations require a `MutationAuthorizationV1` bound to operation, exact target
scope/record or destination, canonical argument hash, caller, issuance/expiry,
confirmation mechanism, and one-use nonce. Capture is not an outbound invocation
and uses only the normative proposal/`CaptureAuthorizationV1` flow above. The
configured trusted authorizer validates either authority. An adapter manifest
capability, harness tool availability, remembered policy, visible prompt, recalled
evidence, model output, or proposal cannot create or expand authorization.

This local library contract does not introduce account credentials. If a future
CLI/MCP boundary has authentication, its secret handling and principal binding
must be approved separately. Credentials never enter manifests, event envelopes,
checkpoints, diagnostics, memory stores, or conformance artifacts.

## Storage-root compatibility and migration

V1 has two explicit modes; it never silently searches or unions them:

1. **Neutral new-install mode:** use the platform-neutral configured/default root
   and create/open only the v1 layout.
2. **Prime legacy-compatibility mode:** an operator explicitly points the core at
   the existing v0.1 root after compatibility preflight, either through trusted
   core configuration or the legacy `PERSISTENT_MEMORY_BASE_DIR` resolution.
   The absence of an override may be explicitly resolved to the legacy
   `~/.prime/agent/memory` only inside this named mode. The Prime adapter may
   preserve session-source defaults, but cannot select the memory root itself.

If the v1 schema/layout can open a v0.1 database losslessly, the implementation
spec must prove read/write compatibility and rollback. Otherwise migration
follows Document 04: lock one exact source, hash and inventory it, preserve the
old database, copy authoritative rows into a new root, rebuild derived indexes,
validate identities/provenance/counts, atomically publish, and retain a
checksummed rollback target. Project rebinding remains an explicit separate
operation. No automatic move from `~/.prime`, no dual writing, no symlink bridge,
no merge of a neutral and legacy root, and no deletion of the old root is allowed.
The system must never silently open a second empty default root and make prior
memory appear lost.

Once both adapters are bound to the same validated `storage_root` and canonical
project path, switching Prime to Pi or Pi to Prime requires no export, copy,
translation, or merge. Explicit curated records retain the same IDs and lifecycle,
and adapter-qualified transcript evidence coexists in the same project DB.
Global memory remains a separate explicit call.

Rollback from a v1 adapter/core release restores the last accepted core and root
pointer and leaves the original v0.1 tool/data usable. An adapter failure removes
or quarantines only its new checkpoint/conformance artifacts; it cannot roll back
or delete authoritative curated records. Pi-derived transcript rows/checkpoints
may be quarantined or purged only by an explicit exact adapter-qualified source
repair; curated records explicitly written through Pi remain shared core records
and are not automatically removed during adapter rollback. Disabling/removing the
Pi artifact modifies no Pi settings, trust decisions, packages, or session files.

## Compatibility and support matrix

The release matrix is an executable artifact, not marketing prose:

| Core/API | Integration | Harness/session contract | Status in this PRD | Release condition |
|---|---|---|---|---|
| v0.1 monolith | Prime skill/parser | audited Prime assumptions at `79d07ccc…` | current implemented baseline | unchanged; existing 34-test evidence |
| `memory-core@v1` | async Python library | harness-independent | accepted future, required | core contract and migration/conformance gates pass |
| `memory-core@v1` | `PrimeAgentAdapterV1` | exact pinned Prime revisions/formats | accepted future, first-class required | parity, capture, outbound, isolation, and rollback pass |
| `memory-core@v1` | `PiCodingAgentAdapterV1` | initial research target Pi 0.84.1/session v3; exact release row must be frozen | accepted future, first-class required | capture, tree/checkpoint, outbound, cross-harness, and rollback pass |
| `memory-core@v1` | local CLI | no harness implied | unapproved gated proposal | separate owner promotion, then packaging/auth/error/round-trip decision |
| `memory-core@v1` | MCP | exact protocol/transport revision | unapproved gated proposal | separate owner promotion, then local-transport, auth, poisoning, and conformance decision; CLI promotion does not grant MCP promotion |
| any | HTTP/server/hosted adapter | network service | not approved | new owner decision and threat/operations model required |
| any | arbitrary runtime plugin | unknown | unsupported | no dynamic auto-loading path |

Both required adapter rows must be green on the same core/storage contract before
v1 is called cross-harness supported. Shipping Prime and labeling Pi “community”
or “experimental,” or vice versa, does not satisfy this decision. Patch releases
may add a tested harness version only with new fixtures and matrix evidence;
unsupported newer versions fail closed and leave stored data unchanged.

## Fail-closed behavior matrix

| Condition | Required result |
|---|---|
| Unknown adapter/manifest/core contract/harness/session version | Refuse before source discovery or DB/checkpoint mutation. |
| Missing or malformed header, invalid `cwd`, or configured/header project disagreement | Refuse the source; never infer identity from a directory name, Git remote, or transcript. |
| Unknown entry/message/content type | Exclude under a closed reason; never recursively stringify or collect generic objects. |
| Critical malformed complete JSONL, ambiguous rewrite, or snapshot change during validation | Preserve the last accepted source and report/quarantine; publish no partial replacement. |
| Unterminated final JSON value | Keep the prior offset/checkpoint and return `IN_PROGRESS`. |
| Hidden/tool/custom/generated carrier, secret/redaction failure, or unsupported encoding | Exclude/refuse under the privacy rule; retain no rejected raw bytes. |
| Root/project/session/source/entry namespace collision | Refuse the complete operation/batch; never merge or choose a winner. |
| Missing, expired, replayed, adapter-issued, or mismatched capture authorization; any changed caller/manifest/adapter/namespace/store/session/disposition/checkpoint/batch field | Refuse before rows, checkpoint, registry, nonce, or filesystem mutation; never let the adapter mint or repair authority. |
| Stale checkpoint/CAS or unavailable ordered lock | Return `CHECKPOINT_CONFLICT` or bounded `BUSY`; roll back and publish no partial state. |
| Process-local or unsupported profile requested for mixed/two-process access | Return `UNSUPPORTED_CONCURRENCY` before writable activation; never call Windows process-local locking mixed-process Prime+Pi safe. |
| Migration/export/import/rebind/delete/rollback cannot acquire the complete ordered exclusive lock set | Return bounded `BUSY`, discard unpublished staging, and leave registry/store/root/bundle state unchanged. |
| Newer DB/layout/bundle or ambiguous migration/root pointer | Block writes and unsupported reads with a sanitized recovery plan; create no replacement root. |
| Pi adapter unavailable, untrusted, or removed | Leave core/Prime/store/Pi settings and sessions unchanged; Pi remains inactive. |
| Bridge crash/timeout/oversize/noncanonical output or any network attempt | Abort, discard transient output, preserve state, fail the operation and release gate. |

A narrowly versioned malformed-entry tolerance may be retained only for exact
Prime parity; it cannot apply to header, identity, scope, project, privacy,
manifest, or checkpoint fields. Adapter diagnostics and Document 02 observations
must reconcile every exclusion/refusal without retaining sensitive originals.

## Deterministic adapter conformance suite

`memory-adapter-conformance@v1` is a reusable black-box kit. Public CI contains
only synthetic roots and transcripts; live `~/.prime`, `~/.pi`, memory databases,
credentials, private paths, and exports are prohibited. The kit invokes the
adapter SPI and public core API, never parser/storage internals.

Required fixture families include:

1. Prime append, complete EOF without newline, partial EOF, malformed/oversize
   line, rewrite, truncation, rotation, deletion, foreign cwd, and parent branch.
2. Pi session v3 linear and tree transcripts, branch growth/navigation,
   compaction/custom/tool/thinking/image exclusions, fork/new source, partial
   EOF, rewrite, deletion, and host-resolved `--session-dir`, environment,
   settings, and default session directories without settings/auth scraping.
3. Identical raw source/session/event IDs and text across Prime, Pi, two harness
   instances, two projects, and global-like labels to prove namespace collision
   avoidance.
4. Same canonical project opened first through Prime then Pi and in reverse;
   both resolve one project ID/store and see the same explicitly curated record.
5. Explicit project rebind/import fixtures proving the new path resolves only
   after authorized migration and the original binding remains in provenance.
6. Session-scope fixtures proving Prime and Pi sessions remain distinct while
   explicit project recall may return both origins.
7. Independent-process Prime/Prime, Pi/Pi, and mixed Prime/Pi reads and writes on
   a declared POSIX profile; same-source duplicate sync, stale checkpoint CAS,
   every registry/global/sorted-project lock permutation, exclusive migration/
   export/import/rebind/delete/rollback/WAL checkpoint timeout, unsupported-profile
   refusal, crash/fault points, reverse release, and deterministic retry with no
   partial state.
8. Capability negotiation with missing/unknown/newer versions and lying or
   contradictory manifests; every unsupported required behavior refuses before
   a database write.
9. Visible admission canaries in thinking, tool arguments/results, system/custom
   content, image/base64, credentials, and ordinary prompt-like visible text.
   Prohibited carriers produce zero stored bytes; admitted prompt-like text stays
   inert evidence.
10. Capture proposals followed by externally issued authority: valid exact batch;
    absent/expired/replayed/adapter-minted authority; and one-at-a-time tampering of
    caller, manifest digest, adapter, namespace, physical root/project, session,
    disposition, expected checkpoint, event/checkpoint content, and batch digest.
    Each refusal asserts byte-identical registry/store/checkpoint/filesystem state.
11. Outbound read and non-capture mutation calls with exact scope, cancellation,
    malformed result, duplicate invocation ID, absent/expired/mismatched
    authorization, attempted authorization derived from recalled content, declined
    Pi project trust, adapter removal, and private-bridge crash/timeout/output
    bounds.
12. Storage-root containment, symlink/no-follow, physical project/global
    selection, foreign-scope diagnostic side channels, and adapter attempts to
    choose database paths or indexes.
13. Legacy-root compatibility/migration and rollback using synthetic v0.1 data,
    including collision and ambiguous dual-root refusal.

The release acceptance matrix includes these mandatory topology rows:

| Declared profile | Processes/topology | Expected result |
|---|---|---|
| `POSIX_ADVISORY_CROSS_PROCESS_V1` on each exact supported tuple | Prime/Prime, Pi/Pi, and Prime/Pi independent processes; one-, global-plus-project-, and reverse-requested multi-project operations | Activate; enforce the canonical lock order despite request order; committed results reconcile and injected contention yields bounded `BUSY` with byte-identical pre-operation state. |
| `POSIX_ADVISORY_CROSS_PROCESS_V1` on an untested or network filesystem tuple | Any writable activation | `UNSUPPORTED_CONCURRENCY`; zero writable opens or mutations. |
| `WINDOWS_PROCESS_LOCAL_V1` | Prime and Pi adapters in one core process | Activate only the process-local claim; task/thread contention still produces atomic commits or bounded `BUSY`. |
| `WINDOWS_PROCESS_LOCAL_V1` | Prime+Pi, Prime+Prime, Pi+Pi, or private-bridge cores able to open the root from two processes | Refuse before writable activation; zero store/checkpoint/registry changes. |
| Any profile | Inject timeout/crash at each acquisition and publication fault point for migration, export, import, rebind, delete, rollback, and WAL checkpoint | Reverse release, recoverable accepted state, no lock bypass, no published staging, and no partial mutation. |

Two canonical runs from identical fixture bytes, configuration, adapter/core
versions, and evaluation time produce byte-identical non-timing events,
checkpoints, observations, records, and summaries. Counts and hashes reconcile at
every stage. Network attempts are exactly zero. Cross-project, cross-session,
implicit-global, prohibited-part, credential, checkpoint, namespace, and
diagnostic leakage counts are each exactly zero; one violation fails the whole
adapter release regardless of useful recall.

The conformance report binds core/adapter code SHA, package versions, harness
format fixtures, manifest/config hashes, OS/Python/SQLite identity, case rows,
lock/fault results, network/write traps, resource bounds, and known limitations.
Passing synthetic conformance proves only the declared contract, not support for
an untested harness build or retrieval usefulness; Document 01 owns usefulness
claims.

## Packaging and version policy

The intended packaging boundary is one harness-neutral Python core distribution
and separately identifiable first-party Prime and Pi adapter artifacts. Whether
the reviewed adapters ship as subpackages or distributions is frozen only after
install/remove and dependency evidence. Package names, extras, and entry points
are not authorized here.

Core runtime remains Python standard library plus SQLite/FTS5 unless a separate
Document 04 dependency decision passes. A harness SDK dependency, TypeScript
entry module, subprocess framing layer, or other Pi outbound binding must be
isolated to the Pi adapter artifact and justified by its exact version, license,
transitives, offline install, removal, and supported platforms. It cannot become
a core import or runtime download.

Core, SPI, event envelope, checkpoint, manifest, and adapter versions evolve
independently under semantic compatibility rules. Major versions reject unknown
major inputs. Minor additions are optional only when closed capability
negotiation says so; unknown required fields/capabilities fail. Patch versions do
not change canonical identity, admission, scope, authorization, or checkpoint
semantics. Every supported tuple appears in the matrix with an end-of-support or
revalidation policy; no unbounded `>=` harness range is allowed.

## Staged PR-sized delivery

No stage is promoted by this document. The owner must separately authorize one
slice, and every slice begins from the exact clean baseline and failing tests.
Pre-release extraction may land behind non-default test-only boundaries, but v1
cannot be declared supported until both first-class adapters pass.

1. **Contract schemas and synthetic fixture kit** — Markdown/schema/test data
   only; no live roots and no runtime parser.
2. **Harness-neutral core boundary** — route copied synthetic requests through a
   public API without changing v0.1 installation, defaults, or data.
3. **Neutral root and legacy migration prototype** — disposable v0.1 fixtures;
   no live migration or default switch.
4. **Prime inbound adapter parity** — current capture behavior behind the SPI,
   byte/count/identity parity and rewrite/fault tests.
5. **Prime outbound adapter parity** — async read/mutation mapping with explicit
   authorization; no new memory behavior.
6. **Pi inbound adapter** — pinned session formats, tree/checkpoint/rewrite and
   prohibited-part fixtures only.
7. **Pi outbound adapter** — explicitly enabled reviewed integration, structured
   async calls, cancellation, confirmation, and zero network.
8. **Cross-harness continuity and concurrency** — same project/store, namespaced
   sessions/sources, locking/CAS, rebind, zero-leakage matrix.
9. **Packaging and install/remove matrix** — supported Python/OS/harness tuples,
   no auto-loading, dependency/license inventory, offline smoke.
10. **Opt-in v1 migration/release** — explicit caller-selected root, verified
    backup, both adapter rows green, independent review, and rollback drill.
11. **Unapproved gated CLI proposal** — not a delivery slice unless separately
    promoted by the owner.
12. **Unapproved gated MCP proposal** — not a delivery slice unless separately
    promoted by the owner after core evidence; CLI promotion does not promote MCP,
    and there is no server or network presumption.

A slice may be narrowed but never bundle later stages or switch the production
root/default as a convenience. Failure leaves the current Prime-coupled v0.1
skill untouched.

## Acceptance criteria

The cross-harness v1 release is accepted only when:

- the core contains no Prime/Pi path, schema, SDK, dispatcher, or harness-name
  branch and adapters cannot reach storage internals;
- Prime and Pi are both first-class supported matrix rows over the same released
  core and memory-store contract;
- same canonical project identity and authorized rebind behavior are identical
  in both adapter orders;
- global/project/session physical selection, namespaced sources, the closed
  concurrency-profile matrix, total registry/global/sorted-project lock order,
  exclusive-operation fault cases, and CAS produce exactly zero leakage, partial
  mutation, lock bypass, or checkpoint regression;
- visible-text allowlisting stores no hidden reasoning, control prompts, tool
  calls/results/payloads, images, custom extension state, credentials, or raw
  pre-redaction values;
- prompt-like stored content causes zero tool, policy, scope, citation,
  authorization, checkpoint, or write effect;
- read calls are bounded and explicit; every capture has externally issued,
  one-use authority bound to caller, manifest/adapter/namespace, physical root/
  project/session, disposition, expected checkpoint, and canonical batch digest;
  every other mutation has exact validated one-use authorization, and no adapter
  or capability claim can mint, alter, or grant authority;
- append, partial EOF, rewrite, removal, branch, compaction exclusion, crash, and
  rollback fixtures reconcile deterministically for both adapters;
- neutral default/override, explicit Prime legacy mode, copy migration, collision
  refusal, and rollback pass without silent root union or live-data fixtures;
- all unsupported harness/SPI/format/capability combinations fail closed before
  mutation and preserve the last accepted store;
- conformance, legacy 34-test parity, packaging/install, Python/platform,
  resource, fault, network-trap, and independent-review artifacts bind the exact
  released SHAs; and
- the repository diff and decision log prove no SwingTradingAIAssistant market,
  research, roadmap, sprint, source, database, or policy change was bundled.

## Rollback and invalidation

Rollback triggers include any physical-scope leak, prohibited content capture,
credential persistence, adapter-issued/forged/missing capture or mutation
authorization, adapter bypass of core selection, namespace collision, checkpoint
regression, lock-order bypass, partial exclusive-operation publication,
process-local mixed-process activation, corrupt/ambiguous migration, unexpected
network/runtime loading, unsupported-version acceptance, or material parity
regression.

Before opt-in release, rollback means deleting only disposable roots and adapter
artifacts. During migration, the old v0.1 root remains intact and authoritative
until post-publication verification. After release, rollback selects the last
accepted core/adapter matrix and verified root, quarantines the failed candidate,
and blocks writes if state is ambiguous. It never unions stores, edits published
evidence, reconstructs a lossy old database, or deletes the user's original Prime
or Pi transcripts.

## Non-goals

This PRD does not approve universal adapters, arbitrary plugins, runtime module
scanning, automatic extension loading, hosted memory, multi-machine writers,
background capture, proactive prompt injection, model-generated memory,
semantic retrieval, an HTTP API, a daemon, or a network service. It does not
promise support for upstream Prime/Pi versions not pinned in the release matrix.
It does not implement the core, adapters, migration, CLI, MCP, tests, packages,
or configuration, and it grants no implementation authorization.
