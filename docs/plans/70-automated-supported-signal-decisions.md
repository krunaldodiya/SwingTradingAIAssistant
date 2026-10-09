# Plan 70: automated supported signal decisions

Status: accepted bounded specification under [Issue #299](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/299), Milestone 47. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research policy, provider provenance, private credentials and public decision contracts. Base: `9183bf4b82d4163935ad862c4774ea996eadb4dd`.

## Outcome and consumer

A human CLI user and any compatible AI-agent harness can submit retained, admitted current-stock observations to the same versioned contract and receive a deterministic, source-bound result:

- `RESEARCH_CANDIDATE` when every automated safety gate and the bounded causal policy pass;
- `NO_TRADE` when a required gate or causal condition is proved to fail; or
- `UNKNOWN` when a required source, identity, time, or data-quality condition cannot be established.

Every result contains a bounded explanation ledger. It identifies the rule, result, decisive and supporting evidence, policy-derived measurement, source/time/identity references, and a human-readable deterministic explanation. It distinguishes a proved rejection from unavailable or conflicting evidence. The ledger never emits credentials, raw provider responses, arbitrary exceptions, private paths, or full raw bars.

This is the first working G03/G04 slice. It is a research-candidate policy, not an order, position-size calculation, target, profitability claim, or contextual financial recommendation. An AI consumer may turn these structured reasons into natural language, but it cannot override a hard failure or invent facts.

## Authority, source decision, and scope

The owner's October 9 direction requires automatic research through already configured BharatStock, Upstox and Angel One services without asking an operator to stage exchange files or provide credentials on a command line. The existing repository already has bounded BharatStock history and Upstox corporate-action paths. This plan adds only the documented Upstox Full Market Quotes V3 endpoint to that existing Upstox boundary. Angel One is unnecessary for this slice.

| Evaluation | Result |
| --- | --- |
| Expected value | Obtain current exact-identity quote, depth and circuit facts that retained completed-session research cannot supply. |
| Scope fit | Supplies the missing G03 current-tradability, quote-integrity and current-depth evidence for one admitted NSE equity. |
| Material risk | A live provider may be unavailable, stale, misbound, malformed, rate-limited or expose a private access token. |
| Smallest alternative | Preserve Sprint 52's `UNKNOWN`/`NO_TRADE` output and add no provider effect or candidate policy. |
| Decision | Accepted: one bounded Upstox quote read per V3 invocation, with strict identity/time/schema checks and no fallback. |

The source contract is limited to:

1. The retained BharatStock `CURRENT_STRUCTURE` observation for exact canonical identity, the current 21 completed sessions, and causal structure.
2. A new Upstox Full Market Quotes V3 request to `GET /v3/market-quote/quotes` for exactly `NSE_EQ|<ISIN>`. The official API documents a 500-instrument maximum and exchange snapshots; this contract makes exactly one-instrument requests. The response's `instrument_token` and `symbol` must bind the retained ISIN and effective NSE symbol. [Upstox Full Market Quotes V3](https://upstox.com/developer/api-documentation/get-full-market-quote-v3/)
3. One direct BharatStock history request ending at the retained observation's latest completed session. It supplies only provider-observable completed history and rolling price-volume measurements; it does not prove an exchange listing date.
4. One strict Upstox corporate-actions request for the retained ISIN. It supplies only the provider's documented dividend, bonus, split and rights records and their announced/effective/record dates. It is not a general disclosure, surveillance, news, or event-risk feed. [Upstox Corporate Actions](https://upstox.com/developer/api-documentation/get-corporate-actions/)

No NSE downloader, browser automation, manual source staging, new provider, token handoff, source fallback, persistence/replay model, or source-origin attestation system is introduced. Upstox's published instrument model identifies `NSE_EQ` equity instruments by exchange, ISIN and unique instrument key; the contract accepts only that exact segment/type identity. [Upstox Instruments](https://upstox.com/developer/api-documentation/instruments/)

## First working slice and effect bound

The public V3 SDK accepts only an absolute storage root plus retained observation handle(s), just like V2. It accepts no raw quote, history, corporate-action, symbol, ISIN, safety boolean, endpoint, token, threshold or caller-authored decision data.

After all local retained-record and causal admission succeeds, one invocation may perform at most four serial provider HTTP reads:

1. one Upstox full quote;
2. one BharatStock identity read and one history page for a 420-calendar-day request window; and
3. one Upstox corporate-action read.

The 420-day request has fewer than 1,000 possible calendar rows, so the history adapter must complete in its identity read plus one bounded page. Any provider rejection, malformed response, source-time mismatch, or token failure stops later provider effects and returns the associated `UNKNOWN` rule; a proved safety-policy failure also stops later provider effects and returns `INELIGIBLE`. Neither path retries or substitutes a source. A fresh result is current at invocation and is not presented as knowledge available at an earlier observation time.

`EnvironmentAccessTokenProvider` remains the sole credential source. The token is read lazily, held in a redacted `AccessToken` object and revealed only inside an Upstox HTTP adapter when constructing the authorization header. The tool writes no credential, quote, history, or corporate-action data to storage in this slice.

## Frozen V3 safety policy

Policy identifier: `supported-signal-safety-policy@v1`. Values are fixed in code and result identity; callers cannot tune them. They are conservative research-safety gates, not execution-capacity, manipulation, suitability or expected-return claims.

| Rule ID | Required evidence and deterministic rule | Pass / fail / unknown meaning |
| --- | --- | --- |
| `CANONICAL_NSE_EQUITY_IDENTITY` | Retained packet has one valid `NSE` / `EQUITY` / `EQ` member and its effective symbol, mapping and structure source all bind. | Invalid local admission is terminal; unavailable admitted structure is `UNKNOWN`. |
| `CURRENT_UPSTOX_QUOTE_BINDING` | The one V3 quote response is `success`, contains exactly one `NSE_EQ` quote, and its `instrument_token` is `NSE_EQ|<retained ISIN>` while its symbol equals the retained effective symbol. | A failed equality or invalid quote is `UNKNOWN`, never a substituted security. |
| `CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY` | Provider timestamp is an aware instant within 15 minutes of adapter retrieval; price, circuits, top-of-book prices/quantities and last-trade time are finite, nonnegative where applicable, internally coherent, and quote price lies strictly between positive lower/upper circuit limits. | Schema, time, identity or coherence failure is `UNKNOWN`; a direct policy negative below is separate. |
| `PROVIDER_OBSERVABLE_HISTORY` | BharatStock's returned sessions are unique, end exactly at the retained latest completed session, and contain at least 252 valid completed rows. | Fewer rows, an endpoint mismatch, invalid ordering/corruption or unavailable source is `UNKNOWN`. This is provider-observable completed history, not proof of listing age. |
| `ROLLING_CASH_TURNOVER` | On the newest 20 returned completed rows, calculate the median of source-reported close × volume. The median must be at least INR 10,000,000 (one crore). | A below-threshold observed median is `INELIGIBLE`; absent/corrupt/misaligned rows are `UNKNOWN`. The metric is a research-liquidity screen, not a permitted order size or market-impact calculation. |
| `CURRENT_BOOK_LIQUIDITY` | A positive best bid and best ask must exist; best bid < best ask; relative spread `(ask - bid) / ((ask + bid) / 2)` must be at most 2%; and both total buy and total sell quantity must be positive. The documented response may contain one through five ordered levels per side; this rule uses the best valid pair. | A measured depth/spread failure is `INELIGIBLE`; missing/malformed quote evidence is `UNKNOWN`. It does not prove fill probability. |
| `LOW_PRICE_AND_CIRCUIT_DISTANCE` | The NSE-equity last price is at least INR 20. Its distance to both circuit limits, divided by last price, is at least 2%. | A measured price or circuit-distance failure is `INELIGIBLE`; unbound/invalid values are `UNKNOWN`. This screen does not label a stock manipulative. |
| `SUPPORTED_CORPORATE_ACTION_BLACKOUT` | Strict Upstox corporate-action data is available. No supported dividend, bonus, split or rights event has an effective date within seven calendar days before or after the retained decision session. | An observed blackout event is `INELIGIBLE`; unavailable, corrupt, stale or ambiguous event data is `UNKNOWN`. Passing means no event of these provider-supported types was observed in this window; it does not clear all event risk. |

The INR denomination applies only after exact `NSE_EQ` identity is established. The policy reports calculated threshold comparison values as derived evidence; it does not redistribute provider payloads. Circuit and spread threshold checks compare the underlying Decimal values directly, without accepting a rounded quotient as evidence. The rule never applies to another exchange, segment or asset class.

Before any quote Decimal is canonicalized, rendered or used in policy arithmetic, the strict adapter requires a finite representation of at most 192 Decimal-object bytes, 128 coefficient digits, exponent from -128 through 128, and at most 258 fixed-point characters. A violation is malformed quote evidence and therefore yields the closed `UNKNOWN` path without constructing attacker-sized text or arithmetic precision.

Eligibility precedence is fixed: local integrity failure raises only to the closed public operator boundary; the first proved safety-policy failure is `INELIGIBLE` and ends later provider effects; absent a proved failure, any mandatory unavailable or invalid source/evidence is `UNKNOWN`; `ELIGIBLE` requires every rule to pass. A lower-priority provider effect is not opened after an earlier policy or source failure.

## Frozen causal candidate policy

Policy identifier: `supported-signal-decision-policy@v1`. It consumes the existing exact pair through `assemble_setup_evidence_v4` after V3 eligibility. No underlying Plan 47–60 result changes.

A result may be `RESEARCH_CANDIDATE` only when all of the following are true:

1. V3 eligibility is `ELIGIBLE`.
2. The retained pair's continuity status is `SAME_EVENT`.
3. The invalidation status is `NO_CONTRADICTION_OBSERVED`; the ledger explicitly states that this is the absence of one defined contradiction, never proof of validity or profitability.
4. Candidate age is observed and is from one through five completed sessions inclusive. Zero sessions has no independent confirmation; more than five is outside this policy's freshness window.
5. The current relation to the original broken high is observed and `ABOVE`.
6. The unchanged original supporting `SWING_LOW` / `HL` is represented in the current structure, supplies a valid protective-stop reference, and the current quote price is strictly above that reference.

A demonstrated causal failure (changed event, invalidation, stale age, non-`ABOVE` relation, or current price at/below the structural stop) produces `NO_TRADE`. Missing, revised, non-comparable or unsupported pair evidence produces `UNKNOWN`. The output names the structural stop as a reference and its daily-close invalidation condition; it is not an order instruction, broker stop, position size, target, or loss limit.

## G07 analytical-family disposition

| Family | V3 disposition | Reason |
| --- | --- | --- |
| Market Structure and Price Action | `REUSE_REQUIRED` | The existing confirmed upward BOS, continuity, level relation and supporting low answer the narrow causal question. |
| Daily price-volume history and current quote depth | `REUSE_REQUIRED_FOR_SAFETY` | They supply the bounded completed-history, turnover, current spread/depth and circuit facts required by the G03 policy. |
| Existing Volume context | `REUSE_ADDITIVE` | It remains visible through its existing contract but is not silently equated with execution liquidity. |
| Relative Strength, regime and Industry context | `NOT_REQUIRED_FOR_POLICY_V1` | They are not made hidden candidate gates because this one-stock policy has no same-time, policy-specific need for them. Their absence does not change a V3 safety result. |
| Fundamentals, news, surveillance and broader Liquidity/SMC patterns | `DEFERRED` | They need their own source/capability and decision contract. Future #178 and other Future issues remain excluded. |

Every V3 decision includes this scope limitation so a candidate cannot be mistaken for a full cross-stock ranking, fundamental assessment, or comprehensive recommendation.

## Public contracts, compatibility, and explanation ledger

Add additive V3 SDK functions:

```text
evaluate_stock_eligibility_from_record_v3(storage_root, observation)
evaluate_signal_decision_from_records_v3(storage_root, previous, current)
```

Add matching installed CLI commands without changing V2 behavior:

```text
signal-decisions check-eligibility-v3 --storage-root ABSOLUTE_ROOT --observation SHA256 --output json
signal-decisions evaluate-v3 --storage-root ABSOLUTE_ROOT --previous-observation SHA256 --current-observation SHA256 --output json
```

V2 functions and `check-eligibility` / `evaluate` commands retain their existing source-bound `UNKNOWN` / `NO_TRADE` contract. V3 is additive so a harness can opt into its named version without schema ambiguity. V3 success exits `0` for `ELIGIBLE` or `RESEARCH_CANDIDATE`; policy negatives and `UNKNOWN` exit `1`; malformed requests exit `2` with a fixed diagnostic and no partial stdout.

Each V3 result has a closed schema, canonical compact JSON plus LF, a SHA-256 identity over unsigned output, a maximum 128 KiB encoded output, runtime source identity, policy identity, retained observation identity/identities, separately labelled provider retrieval and source times, eligibility/decision state, limitations, and ordered ledger entries. Each ledger entry has only:

```text
rule_id, outcome, reason_code, explanation, evidence_references, derived_measurements
```

`outcome` is one of `PASS`, `FAIL`, `UNKNOWN`, or `NOT_EVALUATED`; the last form records the exact earlier rule that safely stopped a later provider effect.

`derived_measurements` is restricted to policy comparison quantities and values needed to understand the candidate or rejection, including threshold/result pairs and the structural stop reference. Raw provider JSON, full source bars, request headers, tokens, exception text and storage paths are never included. V3 must include at least one ledger row for every required policy gate and every causal condition evaluated.

## Ownership and implementation boundary

The coordinator owns integration, contract interpretation, tracker state, source/policy decisions, final candidate identity and closeout. The expected implementation files are:

- new `market_data/upstox_full_quote_v3.py` and focused quote-client tests;
- additive V3 eligibility and decision modules or V3 functions with new source-at-rest manifests;
- bounded integration with `corporate_actions.py` only where required to keep `AccessToken.reveal()` at the Upstox provider boundary;
- `stock_eligibility.py`, `signal_decisions.py`, `signal_decisions_cli.py`, their V3 manifests and focused tests;
- Plan 70, Sprint 55/roadmap and first-use documentation necessary for the new commands.

Existing V2 schemas, retained observations, BharatStock capture contracts, causal-fact calculations, source records, package dependencies, workflows and CI policy retain behavior. No manual safety package is used by V3. No source payload is persisted. No background monitoring, portfolio/hold/exit evaluation, list orchestration, AI call, ranking, backtest, broker operation, capital policy, new provider or Future issue is added.

## Adversarial evidence matrix

| Risk or scenario | Required result/evidence |
| --- | --- |
| Full positive | Exact local admission, source-bound quote/history/actions, every safety rule pass, same causal event, age 1–5, `ABOVE`, unchanged supporting low and price above reference yield `RESEARCH_CANDIDATE` with a complete ledger. |
| Safety negatives | Independently show below history/turnover/depth/price/circuit/action thresholds yield `INELIGIBLE`/`NO_TRADE` and name the actual failed rule. |
| Causal negatives | Invalidated, changed/replayed/non-comparable event, age 0 or 6, `AT`/`BELOW`, unavailable support or quote at/below reference produce their frozen `NO_TRADE` or `UNKNOWN` outcome. |
| Missing/conflicting evidence | Missing token, 401/403/429, transport failure, stale/provider time conflict, history end mismatch, malformed action/quote, and unavailable retained records remain typed `UNKNOWN`, with no provider fallback. |
| Source substitution and schema abuse | Wrong ISIN, response symbol/key/token mismatch, duplicate JSON keys, unknown/oversized/deep payload, bad number/timestamp, bad depth and changed circuit relation fail closed without raw output. |
| Bounds and precedence | Exact threshold and limit-plus-one checks cover 252 sessions, 20 turnover rows, INR 10,000,000, INR 20, 2%, seven days, age 1/5 and output 128 KiB. Earlier mandatory failures prevent later provider effects. |
| Privacy and effects | Fake token never appears in stdout, stderr, exception surface, canonical result, hashes or test recordings; four-read limit, serial order, no retry/fallback and no files written beyond existing record reads. |
| Interruption/retry/concurrency | Interrupted/failed provider step returns the fixed closed output without partial stdout or retained mutation; independent repeated calls remain deterministic for fixed injected source clocks and inputs. |
| Compatibility | Existing V2 SDK/CLI outputs and installed behavior remain unchanged; V3 SDK and actual installed CLI are exercised with isolated dependencies. |
| Review and delivery | Full final candidate receives independent functional/domain and security/privacy/provenance reviews, all applicable hosted quality/build/installed/private-package/main-admission gates, exact receipts and live tracker closeout. |

## Qualification, pause conditions, and done boundary

A real provider-backed V3 qualification is required for G08 and any claim that Stage 2 is operationally source-qualified. It may run only if the normal execution environment already injects the required existing provider credentials. The receipt records command version, redacted outcome, provider/source identities and timestamps, never market payload or credentials. Missing injection, provider refusal or unavailable market evidence blocks only that qualification claim; it does not justify manual staging, a new secret path, a fake success, or an unbounded retry.

Implementation starts only after this Plan, Issue #299, Milestone 47 and the Delivery Project fields are read back. The owner has authorized ordinary implementation, tests, reviews, PR, hosted gates, merge, publication and closeout. Pause only at a conflicting source/provider boundary, a credential/protected effect problem, material scope expansion, failed review/gate, unavailable live qualification, or residual risk that requires owner acceptance.

The Sprint is done only when every Issue #299 acceptance criterion and this Plan's matrix has current exact-revision evidence, both independent reviews pass, hosted delivery completes, merged main and private package admission are verified, and Issue/Milestone/Project closeout are read back. A source-qualified Stage 2 completion claim remains blocked until the real qualification receipt exists.
