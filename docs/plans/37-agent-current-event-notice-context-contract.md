# Agent current event-notice context V3

Status: implementation contract for accepted Sprint 24 issue #220; review and
release pending. Owner: Krunal Dodiya. Risk: R3. Authority: issue #220, Plans 25,
27 and 34, and the canonical mandatory agent instructions. This additive slice
follows agent V2 (#215); it does not replace those retained contracts.

## Working slice and boundaries

`research-run-current --contract-version v3` wraps the exact V2 price dossier
and its single previous-completed-session fallback. Default V1 and explicit V2,
price facts, comparability and CLI price-based exit criteria remain intact.
Validate 1–10 unique explicit symbols before any effects. Add one independent
current official event acquisition per batch with at least one mapped member.
Reuse the fixed NSE announcements page initialization and one unfiltered Equity
1D CSV GET (previous/current IST calendar dates), existing bounded transport,
strict filename/media/encoding/parser controls and private cookies. No retry,
attachment, polling, new provider, Industry or calendar acquisition on this edge.
Existing price acquisition can still acquire its own calendar and mapping.

After price work, sample an independent UTC event selection time and set an
absolute event cutoff 120 seconds later. Guard both fetches and retention with
the lease and that deadline; require nondecreasing clocks and the same IST day.
The existing transport timeout/byte/cookie bounds remain unchanged. A call
already in flight can finish at its transport bound; late data is not published.
Event selection, CSV observation and archive-owned retention time are separate
from each member's original price selection/cutoff and selected end session.
Never backdate event knowledge into the price window, including lagged prices.
Publisher timestamp strings have unknown timezone (`publisher_timezone=null`);
this projection does not publish or convert them to UTC or effective dates.

The runtime captures the exact validated price packets used by V2. For each
mapped member, reread its exact retained instrument observation, resolve through
`resolve_current_research_binding_v2`, and require equality of the complete
canonical mapping member with the price packet. No projection is trusted as
mapping authority and no admission seal is fabricated. Exact retained mapping
authority is re-read after effects, even when the optional source failed. Mapping date validity
must cover the current event source date. A missing price mapping or expired
mapping yields explicit member-local unsupported context. Corrupt, substituted,
or missing retained evidence for a purported admitted mapping is fatal.

The single CSV feeds at most ten singleton Event V2 retentions under one private
root lease. Singleton bindings preserve each price packet's own schedule identity
without inventing a shared price schedule. Existing immutable Event V2 storage,
aggregate bounds, retry behavior and completion markers are reused unchanged.
The transport retains its existing 4 MiB event limit; before retention this edge
also admits Event V2's stricter 1 MiB artifact, 2,000-row and 4,096-byte field
bounds. Bound violations are closed `SOURCE_MALFORMED` event failures.
Only genuinely producer-admitted retained Event V2 projections may be projected;
canonical mapping, event cutoff, source window, artifact identity and observation
ordering must match before output. Member-local source conflicts remain local.

## Output and failure contract

V3 adds `event_context` to each price member and an `event_observation` batch
record; the existing EVENT_NOTICES context entry is replaced consistently.
Member output contains availability, support, reason, admitted notice count
(null when unsupported/conflicted/unavailable), observation/retention times and
source/mapping/result/retention SHA-256 identities. It contains no notice text,
attachment URLs, publisher timestamp strings, raw CSV, credentials, cookies,
provider bodies or host paths. No-match means only no matching notice in this
admitted snapshot; it proves neither no event risk nor source completeness.
Market Regime and Industry context remain unchanged and are not acquired here.

Closed acquisition failures (including malformed source, deadline and date
rollover) leave independent price facts intact and produce unavailable event
context. Unsafe/held/replaced storage, internal defects, integrity errors and
interruptions fail closed with no partial CLI JSON. Storage authority is checked
before effects and again even when an optional acquisition fails. Unexpected
exceptions are never converted into an optional source failure. Existing CLI
sanitized internal errors remain; interruption propagates without publication.

All NSE-derived output, **even redacted counts/status and provenance**, remains
owner-private for the already accepted local personal/noncommercial use. No
hosted AI disclosure, publication or redistribution is authorized. No live source
call is authorized for this writer assignment. Synthetic local smoke evidence
must not be described as live integration or source qualification.

## Frozen adversarial matrix and delivery

Tests cover: admitted notices and no-match; one and ten members; duplicate and
11-symbol rejection before effects; exact two event HTTP requests; malformed,
unavailable, deadline and rollover; member conflict; canonical/time/window and
forged-projection substitution; lagged price with later event cutoff; missing
mapping; unsafe/held/replaced storage, failure precedence and interruption;
retry after interruption; body-free output; CLI price exit and V1/V2 compatibility.
Use deterministic real parser/mapping/archive paths with synthetic transport.
Format source before refreshing all directly/transitively bound current source
manifests. Preserve every frozen historical source map and retained identity.
Rollback removes the additive selector/module without rewriting retained data.

Writer owns runtime/tests, this contract and the workflow guide. Coordinator owns
notes, memory, governance, full/static/build/installed gates and release. Writer
uses inherited Codex model/settings (unverified telemetry), prepared Python 3.11
`/tmp/sprint24-validation-venv`, no delegation, and focused checks only. Independent functional/domain
and security/privacy/provenance reviews must assess the exact committed bytes;
the author supplies evidence, never self-approval. Stop for any new subsystem,
provider, unbounded transport or conflicting ownership. Broader context,
discovery/scale, sentiment, rankings, signals and orders are deferred.


## Retention temporal failure precedence

Expiry or IST rollover first observed by the Event V2 archive clock is an
optional temporal failure for V3 after source/canonical binding and storage
integrity have passed. `CurrentEventRetentionTimeErrorV2` is a ValueError subclass
with a closed cutoff/rollover code. It preserves the delivered ValueError message
for legacy callers. V3 catches only the typed class, never generic ValueError or
message text.

Precedence is frozen as follows: parse and canonical/source-window binding,
private root/archive authority, stored-prefix shape and all existing object bytes
are validated before a temporal exception. A raw-only prefix must match the
incoming artifact even when expired. A valid durable projection prefix retains
its original knowledge time and existing retry/recovery behavior; corruption in
its projection/receipt/marker remains fatal. Before raising a temporal exception,
recheck the root/archive and the validated prefix. When the archive is absent,
verify continued absence and root authority without creating an archive.
No clamped/backdated clocks, new persistence protocol, changed identity equations,
source retry, weakened cutoff, or generic-error reinterpretation is permitted.
Source and stored-prefix integrity errors remain fatal even when the fresh clock
is expired; publication never relies on time alone to classify an integrity error.
