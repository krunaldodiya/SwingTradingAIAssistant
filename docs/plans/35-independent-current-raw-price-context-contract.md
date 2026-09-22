# Independent current raw price-context contract

Status: **DELIVERED — Issue #188 closed through merged PR #197; deterministic acceptance evidence below; no live-provider proof claimed**
Risk: **R3** — public financial-research evidence, provenance, temporal truthfulness, and provider-effect control.

## Purpose and public boundary

`current-price-context@v1` is an additive, independently callable research fact
for an explicit ordered 1–50 canonical NSE equity cohort.  It reports only
admitted raw completed-session Structure, S0/S20 direction, inclusive-60%
cohort breadth, and literal `INDUSTRY` participation.  It never selects an
index, exposes raw bars, classification rows, paths, credentials, response
bodies, headers, exceptions, or stack traces, and it is not trading advice.

The request is the closed, maximum-64-KiB
`current-price-context-request@v1`: UTC selection time, a UTC deadline at most
30 minutes later and before IST rollover, exact schedule identity, ordered
canonical members, the four fixed questions, and an optional closed Industry
archive reference. Unknown or duplicate JSON fields are rejected. The result
is bounded to 1 MiB and binds ordered and canonical cohort identities,
selection/cutoff/knowledge-time bindings, source/basis/provenance identities,
availability/readiness/reasons, acquisition outcome, and limitations.

Raw basis is exactly `UPSTOX / RAW / 1d-derived-from-retained-1m`; this is not
BharatStock source-reported OHLC, Yahoo data, adjusted pricing, or total return.
For complete N, `ADVANCE`/`DECLINE`/`UNCHANGED` compare `close[S20]` with
`close[S0]`; breadth is broad advance or decline exactly when the respective
count times five is at least N times three. A missing member withholds the
aggregate and never reduces N. Structure reuses the unchanged Plan-31
radius-two, strict-tie, causal close-confirmed mathematics.

## Retention, acquisition, and limits

Retained-only is the default and must read neither credentials nor providers.
`--acquire-missing` is the sole effect opt-in. It is serial, has no retry,
fallback, redirect, polling, or inferred quota, and applies the frozen status
precedence: malformed request before effects; shared auth/authorization/rate,
deadline/cancellation/IST, root/catalog failures stop subsequent effects;
unexpected faults propagate to the #145 internal-error boundary; known
member-local failures preserve independent members; Industry failure is local.

Acquisition requires **already retained exact calendar evidence** for both the
21-session selection and physical monthly plan. Missing coverage returns
`CALENDAR_PREREQUISITE_MISSING` before mapping, raw, action, credential, or
provider effects. This plan does not change the calendar composer/acquirer,
infer weekdays, widen 32/62-day bounds, add a provider/store/replay/attestation
framework, or establish a live provider claim. Bounds are 21 sessions, 64
inclusive calendar days, three months, 10,000 selected minutes/member, 1–50
members, at most `5N+1` mapping/raw/action GETs, and 30 minutes.

Industry reconstruction is existing-only and uses exact named raw/snapshot/
receipt/marker objects under an existing lease. It reconstructs only the current
fixed NSE `INDUSTRY` input and retains the original archive cohort identity
while binding exact equal members to the new ordered raw cohort. Legacy
arbitrary-licence archives are unsupported by this reader; existing legacy
readers and the Industry writer remain unchanged.

## Crosswalk and preservation

| Authority | #188 treatment |
| --- | --- |
| Plan 20 | Preserves historical supplied-cohort regime contracts; no relabel or dependency on its prospective chain. |
| Plan 21 | Reuses only compatible retained corporate-action evidence; the additive strict action path leaves legacy `fetch`, storage, and screen semantics unchanged. |
| Plan 22 | Does not invoke, substitute, or relabel BharatStock/Yahoo/adjusted data. |
| Plan 23 | Uses explicit canonical supplied members; index/category selection remains above the feature. |
| Plan 24 | Uses exact literal `INDUSTRY`, not official Sector; Industry absence is local and never suppresses raw facts. |
| Plan 27 | Reuses its retained-evidence principles and preserves its V4/current readers; this plan neither constructs a V4 request nor changes its combined acquisition path. |
| Plan 31 | Reuses unchanged provider-neutral 21-session Structure mathematics; no alteration to pivot or confirmation rules. |

## Honest evidence limits and rollback

Deterministic temporary-root and network-denied tests may prove request bounds,
no-effect retained-only/prerequisite behavior, strict-status handling, local
Industry failure, arithmetic, and old-reader compatibility. They cannot prove
live Upstox credentials, provider behavior, retained private evidence, or a
historically known market observation; those claims remain separately
authority-gated. Rollback removes only this plan's additive entry points and
leaves valid retained evidence, old readers, writers, manifests, and historical
identities intact.
