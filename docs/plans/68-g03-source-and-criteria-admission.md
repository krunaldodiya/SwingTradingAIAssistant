# Plan 68: G03 source-and-criteria admission

Accepted October 9, 2026 under [Issue #296](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/296),
Milestone 46. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research
provenance and safety-policy design. Base
`a826f530e2d9dde7757e7245edbafd3ba90200e2`.

## Question and smallest usable path

Can the sources already admitted by this repository and the source categories
referenced here support an eligibility clearance for one selected NSE equity? No.
They support bounded identity,
completed-session research, an owner-staged package check, and one narrow event
snapshot. They do not establish the missing source authority, criteria, time
coverage, or claim-specific measurements for G03.

The smallest useful result is therefore a documentation-only admission record.
It identifies the exact data capability that a later G03 contract must acquire
or prove, separates an official source category from an adopted source, and
states the fail-closed behavior while that evidence is absent. It does not add a
second `UNKNOWN` command, a generic source adapter, a threshold, or a stock
verdict.

This resolves one concrete pre-implementation question from
[Plan 63](63-stock-eligibility-safety-readiness.md): what source and criterion
proof is necessary before code can turn a retained research observation into an
eligibility decision. It does not close G03, G04, G06–G12, any signal-phase
obligation, or a whole-tool outcome.

## Authority, source boundary, and evaluation

The owner directed the next non-Future signal prerequisite after Sprint 53.
[Plan 61](61-first-use-gap-reconciliation.md), Plan 63, Plan 66, Plan 67, and
the [architecture eligibility boundary](../architecture-freeze-v1.md#dynamic-stock-list-and-eligibility-boundary)
remain controlling. The current source decision is deliberately narrow:

| Evaluation | Result |
| --- | --- |
| Expected value | Prevent a source category, local digest, relative-volume fact, or missing event row from being treated as a G03 clearance. |
| Scope fit | Resolves the source-capability and criterion-evidence question that must precede a stock-specific eligibility implementation. |
| Material risk | Manual bytes can be stale or misattributed; turnover does not prove execution capacity; a narrow event snapshot does not prove safety. |
| Smallest alternative | Keep the delivered `UNKNOWN` eligibility and `NO_TRADE` decision boundary without adding a source or policy. |
| Decision | Accepted documentation delivery only. Source adoption, acquisition, criteria selection, and eligibility implementation stay separately governed. |

[NSE's research-data list](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Data%20list%20under%20NSE%20Data%20Sharing%20Policy%20for%20Research%20and%20Analysis_20250728.pdf)
identifies securities available for trading and security-wise OHLC/turnover as
research-data categories. [NSE's Terms of Use](https://www.nseindia.com/static/nse-terms-of-use)
prohibit systematic or automated data collection. The data list and pages are
therefore capability references, not this software's licence, source adoption,
or downloader authority. This Sprint obtains no market payload, creates no
credential or source configuration, and makes no request to an NSE endpoint.

Existing [Plan 25](25-current-supplied-cohort-event-notice-contract.md) evidence
remains owner-private, current, bounded to its declared official Equity `1D`
source and exact `known_at` contract. It is reused here only as a limitation:
its `NO_MATCHING_NOTICE_IN_SNAPSHOT` result is not evidence that no event risk
exists. This Plan does not extend its window, endpoint, retention, attachment,
or permitted use.

## Source-capability matrix

The matrix describes capabilities a later contract may evaluate. It neither
obtains the described data nor treats a local declaration as publisher proof.

| Evidence domain | Existing source or reference | What the capability could establish after separate admission | What it cannot establish | Required timing and provenance boundary |
| --- | --- | --- | --- | --- |
| Canonical identity and current research binding | Existing admitted mappings and retained `CURRENT_STRUCTURE` observations | The selected ISIN/exchange/effective-symbol identity and the existing completed-session research linkage | Unrestricted tradability, listing age, surveillance status, liquidity, price policy, or eligibility | Preserve each producer's source identity, source basis, effective mapping interval, and archive-owned `known_at`; do not convert a symbol into a safety certificate. |
| Current securities-available-for-trading reference | [NSE securities available for trading](https://www.nseindia.com/static/market-data/securities-available-for-trading) and the research-data list | A manually and independently permissibly obtained source row could support a claim about the source's current published list at its stated source date | A rule for sufficient listing duration, all trading restrictions, future status, source permission, or a current result after the source date | A future contract must bind the fixed source location, source publication/effective date when supplied, retrieval time, canonical row identity, and owner-private permission basis. This Sprint stages no file. |
| Daily price, volume, and turnover reference | [NSE security-wise archives](https://www.nseindia.com/report-detail/eq_security) and the research-data list | A separately admitted manual source record can support a bounded OHLC, volume, or turnover observation on the source's declared date | Spread, depth, executable impact, order-size capacity, currency/price policy, manipulation, or a universal liquidity rule | Keep exact source date, source basis, retrieval/known time, canonical identity, and any correction/revision status. A source category is not a historical truth claim. |
| Existing volume and price facts | Existing source-reported OHLCV and Plan 39 relative-volume context | The already declared source-reported bar and relative comparison within its own observation contract | Cash turnover, execution liquidity, a low-price screen, an impact-cost calculation, or an eligibility decision | Retain the existing separate source bases and times; no shared cutoff or new price currency claim is inferred. |
| Current event-notice evidence | Plan 25's bounded official Equity `1D` current artifact | One source-bound snapshot result for the selected member, with its existing source, `known_at`, and source-use limits | Complete event coverage, semantic event classification, a blackout interval, event absence, or safety clearance | Its published/source time and retained `known_at` remain distinct; stale, future, missing, conflicting, or unlicensed evidence stays unavailable. |
| Owner-staged safety package | Plan 67's `stock-safety-evidence inspect` fixed local package | The exact safe local bytes, the fixed field shape, and literal staged-list observations bound to an admitted identity | Publisher origin, source permission, currentness, listing-duration policy, liquidity, price policy, event coverage, or eligibility | SHA-256 binds bytes, not source authority. There is no source URL or source-published time in the V1 package, so it cannot supply them by inference. |

A source record must keep four different time concepts separate whenever they
exist: the source's effective date, the source's published time, the repository
or operator retrieval time, and the retained observation's `known_at`. Missing
one is an explicit evidence limitation. A newer retrieval cannot make a fact
historically known at an earlier decision point.

## Criteria that remain unselected

G03 needs claim-specific rules. This Sprint documents the evidence each rule
would need; it does not select values, weights, windows, or outcomes.

| Claim requiring a later rule | Evidence and policy questions that must be frozen first | Current Sprint 54 result |
| --- | --- | --- |
| Current listing/tradability | Which exchange-published state is relevant; which canonical identity/date it binds; how source currentness and exceptions are handled; and what source use is permitted | No current stock is cleared. A list row, staged row, or mapping is not a tradability verdict. |
| Sufficient listing duration | The concrete safety risk addressed; a supported listing-date source; effective-date and correction semantics; the calendar/business-session definition; and a justified minimum rule | No listing-duration threshold or cutoff is selected. A 21-session feature window is not a listing-age proxy. |
| Execution liquidity | The intended research claim; any required execution context; supported measurements such as turnover, spread, depth, or impact; their time basis; and separately justified criteria | Relative volume and OHLC/turnover are not promoted into execution adequacy. Any rule tied to order size belongs to a separately scoped execution/capital decision. |
| Price integrity and low-price concern | The risk addressed; admitted price basis/currency; corporate-action and correction treatment; a deterministic evidence-backed rule; and its insufficiency behavior | Positive or finite prices remain ordinary data-quality facts. No low-price or manipulation rule is selected. |
| Event-risk coverage | The event classes, source coverage, source and effective times, affected interval, correction handling, and deterministic treatment of unclassified notices | Existing current snapshot evidence keeps its narrow meaning. A missing matching notice does not clear event risk. |
| Overall eligibility precedence | Which capabilities are mandatory for the chosen claim, exact refusal precedence, and the distinction between missing evidence and a proved stock-specific negative | The existing public result remains `UNKNOWN`; the decision path remains `NO_TRADE`. |

No confidence score, optional analytical confirmation, index membership,
market capitalization, plain price, or caller-authored boolean fills these gaps.
Future #178 is still excluded, so company-fundamental data is not imported as a
substitute for the missing evidence.

## Fail-closed handoff

The following is a required design boundary for a future eligibility contract,
not a new API or a change to the delivered `stock-eligibility@v2` schema:

1. A malformed request, unbound identity, or invalid retained evidence must fail
   before a stock-specific decision.
2. Missing, unverified, unsupported, stale, future-dated, or conflicting
   mandatory source evidence must remain distinguishable from a proved negative
   condition and must prevent a clearance.
3. A source row may supply only the claim named by its admitted contract. It
   cannot silently supply a different policy input, a source-permission claim,
   or a historical knowledge claim.
4. A stock-specific negative may be reported only after a future policy defines
   the condition and proves the required evidence. It cannot be inferred from
   absence, a digest, a heuristic, or an uncalibrated threshold.
5. Until every mandatory capability and criterion is separately admitted, the
   current `UNKNOWN` eligibility and `NO_TRADE` actionability boundary applies.

## Adversarial claim matrix

| Attempted inference | Required disposition |
| --- | --- |
| Current index selection, canonical mapping, or a provider symbol proves eligibility | Reject. Selection and identity do not bypass a safety gate. |
| A row in an available-for-trading list proves a sufficient listing age or unrestricted future tradability | Reject. It is at most a source-date list observation after separate source admission. |
| A 21-session window proves IPO/listing history | Reject. Feature sufficiency and calendar listing duration are different claims. |
| Relative volume, nonzero volume, closing price × volume, or one turnover row proves execution liquidity | Reject. These do not establish spread, depth, impact, purpose, or any justified criterion. |
| A positive price or low price proves or disproves manipulation risk | Reject. A claim-specific price-integrity rule and evidence are missing. |
| No matching Plan 25 notice or absence from a staged ASM/GSM list proves no event/restriction risk | Reject. Both are bounded observations with explicit coverage limits. |
| A local SHA-256, manifest-like declaration, or manually supplied URL authenticates source origin or permission | Reject. Byte integrity does not authenticate publisher origin or authorise use. |
| A later retrieval establishes what was known at an earlier decision point | Reject. Preserve the exact source/effective/retrieval/`known_at` distinction. |
| This documentation delivery closes G03 or permits `ELIGIBLE` / `ACTIONABLE` output | Reject. It establishes only the next admission boundary. |

## Delivery, ownership, and later boundary

Root owns Plan 68, the Sprint 54 record, current-roadmap status corrections, and
this documentation-only candidate. No runtime code, tests, package metadata,
workflow, source-at-rest manifest, credentials, or data files change. The
verification is direct source/contract inspection and `git diff --check`, plus
complete independent exact-byte R3 functional/domain and
security/privacy/provenance reviews.

Markdown paths retain their configured exclusion from the long quality, build,
main-admission, and OCI-publication pipelines. The normal PR still requires
applicable lightweight security review/checks, exact merge/readback, live
Issue/milestone/Project closeout, and retained evidence. It does not requalify a
runtime image or claim a code-release receipt.

A successor may begin only with its own governed Issue and contract that names:

- the exact claim to make and the smallest evidence-backed criterion;
- an admitted source, permission/use basis, bounded acquisition method, and
  source/effective/retrieval/known-time contract;
- handling for missing, stale, future, revised, conflicting, and unsupported
  evidence; and
- a versioned eligibility/output contract and adversarial verification matrix.

Pause before any new provider, credential, automated collection, source-origin
attestation design, threshold calibration, actionability, broker effect,
persistence/replay model, or capital/execution policy. None is authorized by
this Plan.
