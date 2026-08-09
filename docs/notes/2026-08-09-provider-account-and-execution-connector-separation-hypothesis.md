# Provider, account, and execution connector separation

Date: 2026-08-09

Status: **open — proposed architecture hypothesis**

## Context

The product may eventually analyse a user-supplied, supported Nifty 50 equity
holding snapshot.  The architecture freeze already permits that *read-only*
portfolio-monitoring outcome, but its snapshot contract and broker boundary are
not specified.  This note records a narrow hypothesis for evaluating that future
work; it neither selects a broker nor authorizes an integration.

The product remains a deterministic Nifty 50 equity swing-research tool.  It
does not place or manage orders, make autonomous decisions, support futures or
options, or give long-term portfolio advice.  No account, balance, identity, or
credential has been used or retained for this research.

## User problem and expected value

A household or multi-user deployment may need a person to see deterministic
research and risk facts alongside their own supported equity holdings without
manually retyping them.  The measurable value to test is whether a validated
snapshot reduces input errors and stale-position ambiguity while preserving
account separation and producing traceable `NO_DATA`, stale, or unsupported
results instead of invented facts.

## Proposed separation of responsibilities

This is a boundary hypothesis, not a design approval.  Any future specification
should keep the following roles separately replaceable and separately governed.

| Role | Proposed responsibility | Explicit boundary |
| --- | --- | --- |
| Shared read-only market-data provider | Supplies public/entitled market and instrument data to the existing deterministic research pipeline. | It is not an account connector, does not receive account snapshots, and does not select trades. |
| Per-account read-only portfolio/account connector | Under that account holder's explicit authorization, retrieves only the defined holdings/positions evidence needed for individualized analysis. Multiple connectors may coexist, but each has its own authentication, authorization, rate limits, identity mapping, audit trail, and failure state. | It cannot read another account, share credentials/tokens, pool private account payloads, place orders, or silently convert an unavailable response into a zero position. |
| Future execution/order connector | Would be a distinct, separately gated adapter for an explicitly approved future product decision. | It is not proposed for implementation here. Current scope prohibits order placement, modification, cancellation, autonomous execution, and order-management behavior. |

The shared market-data provider and each account connector must have independent
credential/token stores and lifecycle controls.  A connector must bind the
broker's authenticated identity to an application account reference without
using mutable display names as identity.  A user or household boundary is the
default: no cross-account reads, aggregation, cache lookup, logs, error detail,
or AI research packet may leak one account's facts to another.

## Current evidence about Upstox, not a selection decision

The following public documentation was checked on 2026-08-09.  It confirms
available interface claims only; it does not establish production reliability,
licensing, entitlement, suitability, or a permanent provider choice.

- [Historical Candle Data V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)
  documents minute history from January 2022 and a one-month maximum retrieval
  for one-to-fifteen-minute intervals.  That makes Upstox a current
  market-data-provider *candidate* to measure for the existing equity-data
  foundation, not a permanent selection.
- [Rate limiting](https://upstox.com/developer/api-documentation/rate-limiting/)
  and [API error codes](https://upstox.com/developer/api-documentation/error-codes/)
  document throttling and `429`/too-many-request outcomes.  A future connector
  must keep limits and backoff scoped to the relevant provider and account,
  rather than allowing one account to consume another's budget.
- [Holdings](https://upstox.com/developer/api-documentation/get-holdings/) and
  [positions](https://upstox.com/developer/api-documentation/get-positions/)
  are authenticated account-specific GET endpoints.  This is evidence that an
  account connector could be investigated, not authorization to call one or
  proof that its fields meet the product's point-in-time contract.
- The [analytics-token announcement](https://upstox.com/developer/api-documentation/announcements/analytics-token-static-ip/)
  says its documented token is read-only, account-specific, static-IP-gated,
  and has one active token per account.  Those constraints increase isolation,
  revocation, network, and operational requirements; they are not a proposed
  credential design.
- [Upstox Plus](https://upstox.com/plus/) and its
  [terms](https://upstox.com/files/terms-and-condition/plus-pack.pdf) show
  plan-dependent API features and terms subject to change.  The current public
  pages are insufficient to establish a fixed cost or entitlement for this
  product.  Pricing, plan eligibility, rate limits, and applicable commercial
  terms must be rechecked at any procurement or integration decision.
- [General terms and privacy policy](https://upstox.com/terms-of-use-and-privacy-policy/)
  were checked, but this note does not infer a right to redistribute, pool, or
  expose market data.  Shared-data licensing, redistribution, retention,
  processor/controller obligations, and account-data consent need an explicit
  legal/commercial review before any multi-user service is considered.
- Upstox also documents [expired derivative historical candles](https://upstox.com/developer/api-documentation/get-expired-historical-candle-data/).
  That F&O capability is explicitly irrelevant and out of scope for this
  Nifty 50 equity-only product; it is not a provider-selection justification.

The owner rationale that a familiar broker could be convenient is distinct from
the verified facts above.  FYERS, Kite, Dhan, and Angel One are unevaluated
examples only.  This note makes no product comparison and authorizes no work on
them.

## Required future account-snapshot properties

Before a connector can be proposed for implementation, its approved
specification must define all of the following.

- Explicit per-account consent, least-privilege authorization, token rotation
  and revocation, secret isolation, and a prohibition on credential persistence,
  sharing, fixtures, logs, or error text.
- A broker-plus-account identity mapping with stable opaque application account
  references, authorization-time evidence, and an auditable provenance trail
  for source, retrieval time, response/schema version, normalization version,
  and consent/authorization state.  It must avoid storing personal identifiers
  when an opaque reference suffices.
- Point-in-time snapshots: captured-at and effective-as-of timestamps, market
  state, broker source version, and reconciliation state.  A current endpoint
  response must never be represented as historical holdings at an earlier
  cutoff.
- Per-account rate limits, bounded retries/timeouts, outage and fallback
  behavior, and explicit `NO_DATA`, unauthorized, unavailable, stale,
  unsupported-instrument, reconciliation-failed, and partial-snapshot outcomes.
  A manual snapshot remains available when a connector is unavailable, but is
  labelled as user supplied rather than broker verified.
- Reconciliation of broker positions/holdings with the supported, point-in-time
  Nifty 50 equity universe.  Unsupported instruments are isolated and reported
  without silently dropping them, treating them as cash, or importing F&O data
  into equity analysis.
- Controls and tests for tenant/account isolation, access revocation, stale
  data, duplicate or delayed snapshots, partial provider responses, identity
  mismatch, replay, audit-log redaction, and no cross-account leakage through
  storage, caching, metrics, prompts, or exports.

## Alternatives and costs

**Do nothing.**  Keep the current research tool independent of private account
data.  This has the lowest security, licensing, support, and regulatory risk,
but retains manual transcription and stale-snapshot risk.

**Smallest safer alternative.**  Accept a manual user-supplied holdings snapshot
or import under a typed, validated contract, with no broker authorization.  It
must record the user-declared as-of time, source type, validation outcome, and
unsupported or missing fields.  It cannot claim broker verification or solve
timeliness/reconciliation by itself, but it can validate the portfolio-analysis
contract before any external account access exists.

**Connector hypothesis costs and failure modes.**  A broker integration adds
privacy and consent obligations; secret-management and incident-response work;
account and household isolation requirements; provider outages, entitlement and
rate-limit handling; source-schema/version drift; operational monitoring;
maintenance across brokers; and legal/commercial review of market-data and
account-data use.  It also creates point-in-time and correctness risks: delayed
or partial responses, settlement-state ambiguity, stale holdings, corporate
actions, broker identity changes, account mapping mistakes, and accidental
cross-account aggregation.  These risks must be measured against the manual
alternative rather than presumed worth accepting.

## Evidence and promotion gates

This hypothesis remains **open** until all applicable gates are met:

1. The owner approves a bounded product problem and a separate, atomic Linear
   item; it is not added to the current sprint by implication.
2. A specification defines purpose, inputs, output schema, deterministic rules,
   edge cases, acceptance criteria, `NO_DATA`/staleness semantics, and the
   equity-only universe filter.  It must separately specify a manual-import
   baseline before a broker connector.
3. Provider-specific evidence verifies current endpoint scope, OAuth/analytics
   authorization, identity semantics, token revocation, rate limits, account
   concurrency, operational availability, data freshness, and pricing/terms.
4. Security, privacy, licensing, regulatory, and threat-model review approves
   consent, data minimization, secret handling, audit retention, household/user
   separation, incident response, and no-redistribution constraints.
5. Deterministic fixtures and red-green-refactor tests prove tenant isolation,
   provenance, point-in-time behavior, reconciliation, failure handling, and
   no cross-account leakage.  Any live probe requires separate owner approval,
   uses no retained secrets or private payloads, and is not part of this note.
6. An execution connector, if ever considered, has its own owner-approved
   architecture decision, risk/compliance review, specification, atomic work,
   and gates after the read-only path is proven.  It cannot be inferred from a
   read-only connector.

## Consequences / next steps

No code, dependency, configuration, provider credential, account action, API
call, architecture-freeze change, or execution feature follows from this note.
Continue the approved equity market-data work.  Revisit this hypothesis only
through the promotion gates above and with an owner-approved specification.

## Related documents

- [Architecture freeze v1](../architecture-freeze-v1.md)
- [Research vision, validation, and instrument extensibility](2026-08-07-research-vision-validation-and-instrument-extensibility.md)
- [Data foundation and Upstox ingestion plan](../plans/01-data-foundation-and-upstox-ingestion.md)
- [Reference repositories](../reference-repositories.md)
