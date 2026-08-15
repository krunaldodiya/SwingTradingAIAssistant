# Sprint 9 — Market Regime Layer B acquisition decision

Status: **IMPLEMENTED / VERIFIED — TERMINAL DECISION `BLOCKED`; PUBLICATION PENDING**  
Planning base: `b8359f5`

## Goal and architecture placement

Deliver one test-first learning/decision slice that answers whether later Market
Regime Layer B evidence acquisition may proceed. The slice implements the pure
decision and bounded market-data probe, performs the one owner-authorized
supervised probe invocation, seals the reviewed evidence/authorization manifest
in the candidate build, and publishes the evidence-driven terminal decision.
It is not a documentation-only sprint.

[Plan 16](../plans/16-market-regime-layer-b-acquisition-decision.md) is the
implementation-ready contract. Its only terminal states are
`APPROVED_TO_ACQUIRE` and typed `BLOCKED`. Approval is distinct from acquisition,
execution authority, retained evidence, `READY`, admission, `OBSERVED`,
validation, and Market Regime computation. Plans 12 and 13 remain frozen.

## Accepted five-line source evaluation

1. Expected value: test whether one candidate artifact can be reached within a tightly bounded receipt path.
2. Scope fit: the candidate could inform later point-in-time Nifty 50 membership-source research for Market Regime Layer B.
3. Material risk: reachability, status `200`, media type, `%PDF-`, or one digest proves no publisher authority, membership content, historical completeness, correction semantics, identifiers, licence, or permitted use.
4. Smallest alternative: one supervised credential-free GET; no retry, parsing, persistence, catalogue write, acquisition, label, count, or outcome.
5. Decision: the probe may create capability evidence only; the sealed manifest separately determines whether later acquisition may proceed.

The PDF is a **candidate artifact**, not a pre-attested official membership
artifact. `%PDF-` proves only a five-byte prefix.

## Owner authority and supervised probe

Krunal authorized one supervised release invocation containing exactly one
credential-free `GET` of:

```text
https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf
```

The invocation has one attempt, concurrency `1`, a 1,048,576-byte body cap with
one detection byte, a hard 30-second wall-clock cap, zero retries, zero followed
redirects, no credentials, no parsing, no persistence/catalogue writes, and
sanitized receipt output only. An outer monotonic watchdog force-terminates the
probe child process at the deadline; bounded transport waits alone are not the
authorization control.

Exactly-once is operationally enforced by owner supervision and retained release
run evidence. The adapter is not authorization and does not claim replay
prevention. There is no installable live-probe CLI. A failure consumes the
invocation, and a second invocation is forbidden without a new owner
authorization record and new supervised-run evidence.

Probe URL/status/header/body metadata remains only in the `market_data` receipt.
The pure decision sees only an authenticated provider-independent capability
state and identity that must match the reviewed build-sealed manifest.

## One authenticated manifest boundary

Sprint 9 does not accept caller-authored per-gate assessments or caller-supplied
full-acquisition authorization. Plan 16 defines one canonical
`AcquisitionAuthorizationManifestV1` containing:

- frozen Plans 12/13 and exact acquisition-scope identities;
- the reviewed provider-independent capability state/identity;
- one source/PIT evidence-bundle identity;
- one terms/use approval identity;
- one operational-scope approval identity;
- one owner acquisition-authorization binding; and
- one trusted authorization-validation receipt identity.

The sole runtime source is the exact canonical manifest literal sealed in the
`historical_evaluation` build. The initial pin is `None`, which fails closed as
`SEALED_MANIFEST_MISSING`. Neither stdin, environment, configuration, writable
files, nor matching caller-selected digests can replace it. A future approval is
impossible without a reviewed build change sealing the exact manifest bytes and
identity.

The trusted validation receipt is content-addressed by the manifest and bound to
a code-pinned trusted clock source. Capability and prerequisite assessment times
must not be later than the receipt's trusted decision-assessment time, and every
assessment/validation instant must fall within the acquisition authorization's
inclusive/exclusive `[not_before, expires_at)` interval. Replay wall time and
caller time grant no authority. A later executor must validate fresh
execution-start authority independently.

## Smallest decision taxonomy

The reducer stops at the first applicable value in this closed order:

1. `SEALED_MANIFEST_MISSING`
2. `SEALED_MANIFEST_INVALID`
3. `CAPABILITY_EVIDENCE_MISSING`
4. `SOURCE_AND_PIT_EVIDENCE_UNPROVEN`
5. `TERMS_AND_USE_UNAPPROVED`
6. `OPERATIONAL_SCOPE_UNAPPROVED`
7. `OWNER_AUTHORIZATION_NOT_IN_FORCE`

There is one primary blocker and no redundant additional-blocker or per-gate
matrix. This still identifies the first missing acquisition prerequisite while
keeping malformed or unauthenticated authority distinct.

## Plausible one-week atomic sequence

| Order | Slice | Required exit | Current state |
|---|---|---|---|
| 1 | Freeze Plan 16 and Sprint 9 summaries; write RED decision tests | Missing/invalid seal, all seven blockers, both states, identities, temporal boundaries, bounded stdin, and no-side-effect/dependency failures are discriminatory | **COMPLETE** |
| 2 | Implement pure reducer and offline decision CLI | Initial `None` seal fails closed; stdin cannot supply authority; `16 KiB + 1` is rejected before allocation/parse amplification | **COMPLETE** |
| 3 | Write RED probe tests and implement fixed worker/supervisor | Exact receipt rows, media normalization, byte bounds, no redirect/retry/write, outer watchdog, and local slow-stream termination are green; no live-probe CLI exists | **COMPLETE** |
| 4 | Verify deterministic candidate build, then perform one supervised probe invocation | Retained owner authority/run evidence and one sanitized receipt/projection; no retry or raw-byte retention | **STOPPED — invocation consumed; receipt retained, projection absent** |
| 5 | Review and seal actual manifest; reduce and publish actual decision | Reviewed build change contains exact manifest bytes; one canonical terminal report, exact-revision review, and honest limitations | **BLOCKED decision recorded; publication pending** |

A phase boundary is not sprint completion. The real terminal result is not
predeclared. Missing evidence is never filled by inference; an incomplete sealed
manifest produces its first honest blocker.

## Test-first acceptance evidence

RED precedes production implementation. Focused tests must prove:

- the initial missing seal is byte-stable `BLOCKED`, and no input can replace it;
- manifest/capability/receipt mutation and code-pin mismatch cannot approve;
- both terminal states and each first blocker follow the closed precedence;
- assessed and validated times reject before/not-before, future, inverted,
  equal, before-expiry, and at/after-expiry boundaries exactly as Plan 16 states;
- provider HTTP metadata never crosses the `market_data` receipt boundary;
- the fixed URL, one request, one attempt, concurrency `1`, one body cap,
  no retries/redirects/credentials/writes, and every deterministic receipt row;
- exact minimal media-type normalization without an unspecified parser;
- a local slow stream that keeps yielding bytes is force-terminated by the outer
  monotonic watchdog and produces no body hash or second request;
- the offline CLI reads at most `16 KiB + 1`, does not consume or buffer beyond
  that bound, and emits only fixed redacted structural errors; and
- fail-on-call sentinels for Market Regime/Sector reducers and every provider,
  network, filesystem, clock, random, storage, acquisition, and label side effect
  remain untouched; dependency tests reject those reducer imports.

No public label counter or equivalent field exists.
No-label behavior is proven at dependencies and side-effect ports, not asserted
by a caller-visible zero.

The one real probe is release evidence, not a test fixture. Final evidence must
identify the exact candidate revision and distinguish run, pass, fail, blocked,
and not run. Any repair invalidates earlier exact-revision review.

## Candidate actuals

The owner-authorized invocation ran once at
`2026-08-15T14:14:23.152972Z` and completed at
`2026-08-15T14:14:23.606209Z`. Its retained sanitized receipt reported status
`200`, normalized media type `application/pdf`, 775,528 body bytes, a matching
`%PDF-` prefix, body SHA-256
`1b3a52abf5954f4b213f5b555ee8776ff596f0adde0612cfdd5409b109195370`,
zero redirects, credentials, parser calls, filesystem writes, or storage writes,
and receipt identity
`20911a88188cb83b2630c90c0abbbad7f74aaff8b442afc142133bfd12d8babb`.
No raw response body was retained.

That historical run used worker identity
`e83bb1dabeccc3abe676294ba65210eaea2fa26f5c4fff2eda1491104d4e6430`.
That worker could fall through to another resolved address, so its reported one
network call and attempt are unverified. The receipt remains retained historical
output but is inadmissible as capability evidence. The current fixed worker pin
`65026c3d26fd266a9ae92c98cee286825b33023bfefc669753fe6261d6fc41d7`
was not used for the consumed probe, and no rerun occurred. No
provider-independent capability projection was retained or reconstructed.

The build seal therefore remains `None`; no source/PIT evidence bundle,
terms/use approval, operational-scope approval, owner full-acquisition
authorization, or trusted authorization-validation receipt was supplied.
The offline decision CLI returned canonical `BLOCKED` with primary blocker
`SEALED_MANIFEST_MISSING` and report identity
`456d3e08b337220cf20fbd8be3f50ee7d764b80a88a7c0182b5a4ec6afcfc4ff`.
This is the complete Sprint 9 research outcome. It grants no acquisition or
execution authority.

After source finalization, the latest full gate passed 2,512 tests at 92.16%
branch coverage and built both distributions. The latest focused gate passed
119 tests. Formatting, lint, strict Pyright, and Vulture also passed.
Exact-revision review, hosted CI, GitGuardian, merge, and tracker closeout remain
publication gates.

## Lifecycle and later handoff

Sprint 9 creates no market-data migration, no retained PDF, no production source
replacement, no bulk acquisition, and no Market Regime fact. It may retain only
the sanitized probe receipt, provider-independent capability record, supervised
run evidence, reviewed manifest, validation receipt, and terminal report.

A blocked handoff preserves the immutable report, authenticated identities that
exist, the first missing prerequisite group, and retained review/run evidence.
Later work needs new evidence and a new reviewed manifest/build and may not rerun
the Sprint 9 probe without new owner authority.

An approved handoff preserves the immutable report and exact sealed manifest but
still performs no acquisition. A separate executor must authenticate fresh
execution-start authority, remain inside the approved scope and ceilings, and
seal acquired evidence under Plan 13 before any Layer B computation.

## Current repository and tracker truth

Sprint 8 repository delivery remains complete and its historical sprint record
remains immutable evidence of what was known at closeout. Linear now records
ARK-179 and ARK-181 as **Done**; this Sprint 9 record reconciles that current
operational truth without rewriting Sprint 8 history.

The Sprint 9 Linear hierarchy is now direct: parent Task `ARK-183` is **In
Progress**; its child contract Story `ARK-184` is **In Progress** and blocks its
child implementation Story `ARK-185`, which is **Todo**. These tracking states do
not establish implementation, a probe, a decision, review, publication, or
delivery.

The current working tree contains the Sprint 9 specification, implementation,
tests, one sanitized probe receipt, and the terminal `BLOCKED` decision. The
manifest seal remains absent by design and no capability projection was
retained. Commit, PR, hosted checks, merge, and tracker closeout remain pending.

## Explicit exclusions and stop conditions

Sprint 9 does not authorize bulk, alternate-source, retried, credentialed, paid,
or persistent acquisition; PDF parsing or membership extraction; raw-byte
retention; source/content/licence inference; Layer B admission; Market Regime
labels/counts/outcomes; Sector Participation work; recommendations; or changes
to frozen Plans 12/13.

Stop before the supervised invocation if owner authority, fixed scope, outer
watchdog, byte cap, no-redirect/no-retry policy, or redaction cannot be enforced.
Stop after the authorized invocation regardless of outcome. Do not invoke again
without new owner authority. Stop before acquisition and before labels regardless
of the terminal decision.

## Sprint completion gate and residual risk

Sprint 9 remains **PLANNED / IN PROGRESS** until the focused implementation,
slow-stream watchdog proof, applicable repository evidence, one supervised probe
disposition, reviewed build-sealed manifest, actual offline decision,
independent exact-revision review, publication, and sprint/tracker reconciliation
are recorded.

Remaining risk is explicit: exactly-once depends on supervision and retained run
evidence rather than technical replay prevention; the HTTP/PDF envelope proves
no candidate semantics; and a retained validation receipt establishes only its
historical decision instant, never later execution authority.
