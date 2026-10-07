# Plan 63: stock eligibility and safety evidence readiness

October 7, 2026. Sprint50 / [Issue288](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/288),
milestone42. Owner and risk owner: Krunal Dodiya. R3 design, financial research
and provenance. Base `b86dcc1778412f370beb0e23cd52f5c1e818cfa7`.

## Accepted question and decision boundary

Can the current admitted facts establish G03 stock eligibility before an
actionable swing suggestion, and which evidence must be obtained or specified
first? This bounded design sprint resolves that question. It does not implement
eligibility, adopt a market source, select numerical thresholds or close G03.
The owner requested the next sprint; ordinary checks and normal PR delivery are
covered by the standing October7 direction. No additional release approval is
needed for these exact authorized documentation effects.

[Plan61](61-first-use-gap-reconciliation.md) and the
[architecture eligibility boundary](../architecture-freeze-v1.md#dynamic-stock-list-and-eligibility-boundary)
govern. Plan34's necessary-only rule excludes a generic engine whose only output
would repeat existing availability labels. Safety admission must answer the
chosen claim with adequate evidence, rather than add more analytical filters.

1. Value: prevent unsupported admission of actionable suggestions.
2. Fit: resolve the necessary G03 prerequisite for default and explicit lists.
3. Risk: readiness, public documentation or missing notices mistaken for safety.
4. Smallest alternative: inspect and reuse current contracts before new code.
5. Disposition: **accepted design delivery**; eligibility/source code remains
   deferred until its exact criteria, capabilities and evidence are ready.

## Current evidence and exact missing claim

The references below are current-main source/contract inspection, not new
execution or live stock evidence. An existing producer can be reused within its
own admitted scope. It does not inherit a broader safety claim.

| G03 category | Existing evidence and governing source | Missing evidence or decision before actionable admission |
| --- | --- | --- |
| Canonical identity and mapping | `market_data/instrument_snapshot.py`, `current_research_binding_v2.py` and `current_stock_research_v2.py` bind retained NSE_EQ/EQ mappings, effective symbols, ISIN/exchange and selected/known times. | A mapping proves the admitted identity/profile; it does not independently prove unrestricted tradability, listing age, surveillance status or eligibility. Preserve current ambiguity/conflict rejection. |
| Listing and sufficient history | Current V2 selects completed official sessions and independent one/two/21-session price windows; Plans31–32 own feature requirements. A bounded window can report insufficient Structure while retaining independent price facts. | A listing-date/history policy needs an admitted listing source, its identity/knowledge/effective times and a claim-specific sufficient-history rule. A 21-session feature window is neither proof of an IPO date nor a universal minimum listing age. Do not invent a calendar-age cutoff. |
| Data quality and capability | Packet/build/binding validators require exact requested features, mapping, revisions, price basis, sessions and retained provenance. V2 READY is question readiness; source OHLC is reported within its existing contract. | State each chosen capability's required evidence and freshness/coverage rule. No common acquisition cutoff, fully validated corporate-action treatment or all-source quality is inferred from a READY label. An optional analytical absence cannot silently become a mandatory exclusion. |
| Liquidity and turnover | Plan39 and `volume_analysis/current.py` compare the last completed volume with exactly twenty predecessors. Agent V5 adds independently retained RAW analysis context. | Relative volume is not execution adequacy, cash turnover, spread, depth or impact cost. Neither closing price multiplied by volume nor membership establishes those missing claims. A liquidity rule needs supported measurements, its purpose/order-size dependence where applicable, source use, knowledge times and separately justified criteria. |
| Price integrity and low-price concerns | Current price/Structure contracts bind explicit source-reported basis and causal completed-session facts. Existing validators remain mandatory. | A penny/low-price or manipulation-risk screen needs a specified evidence-backed rule. Price or market capitalization alone does not establish manipulation. Do not invent a floor, silently change price basis or import unapproved company fundamentals. |
| Event risk | Plans25/37–38 and `market_data/agent_event_context.py` retain bounded current announcement evidence with explicit source/use/timing limits. | No matching notice in one snapshot is not absence of event risk. A chosen event restriction requires supported event classification, coverage, known/effective time and a justified affected interval; no arbitrary blackout window or sentiment rule is selected. |
| Source authority and temporal validity | Existing retained stores, leases, runtime/binding checks and source-use contracts control each producer. Plans37–38's NSE context remains owner-private, including redacted provenance/counts. | Admit each missing source and its exact permitted use before acquisition or disclosure. Fresh data cannot be made historically known. A cloud assistant is not an automatically authorized recipient; source-specific unknown/stale/conflicting evidence cannot be resolved by fallback or relabeling. |

The architecture also requires correct treatment of very small-cap, newly
listed, thinly traded and otherwise susceptible stocks when an applicable gate
is unsatisfied. There is no admitted capitalization/fundamental threshold in
this sprint. Future178 stays excluded. Index membership supplies selection
provenance, never an exemption from any of the required evidence above.

## Public documentation observations, not source adoption

Official pages were checked on October7. These observations explain why current
facts cannot supply the missing safety claim; they do not establish any stock's
status, permission to acquire lists, a trading strategy or a permanent rule.

- [NSE impact cost](https://www.nseindia.com/static/products-services/indices-impact-cost)
  describes liquidity through execution cost for a specified order size and
  the available order book. A relative daily-volume calculation does not supply
  that information. This is a capability distinction, not a mandate to add
  order-book acquisition or an impact-cost threshold.
- [NSE periodic call auction](https://www.nseindia.com/static/regulations/periodic-call-auction-illiquid-securities)
  publishes its own illiquidity mechanism and criteria. Those regulatory
  classification rules are not adopted as a sufficient swing-trading liquidity
  policy, and membership in an index does not substitute for current evidence.
- [NSE ASM](https://www.nseindia.com/static/regulations/additional-surveillance-measure)
  describes surveillance based on multiple parameters.
  [NSE GSM](https://www.nseindia.com/static/regulations/graded-surveillance-measure)
  describes additional trading restrictions and changes communicated through
  exchange notices. An instrument-master asset-class field cannot establish
  their absence. Neither framework is treated as proof of wrongdoing or a
  new automatic project exclusion.

Before relying on any rule or stock-specific status, check its controlling
notice/version, applicability and temporal/source authority. Earlier circulars
and page timestamps are not promoted into current executable gates. No raw
exchange list, private market payload or new feed was acquired for this design.

## Decision and unknown behavior

**Current decision:** G03 actionable eligibility is not established by the
delivered descriptive research. Existing commands and their schemas remain
unchanged, including explicit limitations. Their READY/MATCH/NO_MATCH/UNKNOWN
states retain existing meaning. No stock receives a new verdict here.

For a later eligibility implementation, an unmet or unknown mandatory safety
requirement must prevent actionable admission. Unknown is distinct from a
proven exclusion; unsupported source evidence must remain distinguishable from
a stock-specific negative. The concrete output contract, precedence and
criteria must be frozen with that implementation. This paragraph preserves the
existing fail-closed invariant; it is not a new eligibility API or ready
algorithm. Descriptive facts remain available within their existing scope.

Reject these shortcuts: Nifty membership as eligibility; volume above its
baseline as liquidity adequacy; a provider symbol as a listing-age/tradability
certificate; no notice as no risk; a reused source digest as source permission;
synthetic fixtures as live qualification; and more optional confirmations as
independent mandatory safety checks. No confidence score fills missing facts.

## Independent lifecycle prerequisite and smallest next work

G05 remains separately open. `current_stock_observation_comparison_cli.py` and
`setup_evidence_v4_cli.py` require an injected observation service. Current
research acquisition does not provide a public production selector for an exact
previous producer-admitted result. Its canonical result serializer omits
`source_bars`; a copied JSON report is not sufficient typed retained admission.

Alternatives and dispositions:

| Alternative | Decision and reason |
| --- | --- |
| Use current descriptive research as actionable eligibility | Rejected: the missing G03 evidence above is material. |
| Add generic caller-authored safety booleans or arbitrary thresholds | Rejected: self-authored claims do not establish source admission or an evidence-backed policy. |
| Repeat live acquisition with an older requested selection time | Rejected: cannot establish original knowledge or the exact previous observation. |
| Treat public result JSON as a retained observation | Rejected: required retained inputs/admission are omitted; hashes alone are not evidence. |
| Investigate exact retained-observation selection using existing bindings first | Selected next feasibility question under G05; no archive/replay design or code is approved here. Specify persistence only if existing retained evidence cannot preserve the required original observation. |

Order subsequent work by readiness, not gap number:

1. For G03, resolve the minimal stock-specific listing/tradability and liquidity
   source capability/use question; define justified claim-specific criteria and
   evidence before code. Reuse current identity/data/price admission. Event
   policy must preserve its actual coverage and timing limits. This is required
   before actionable suggestions; it need not stop an independent descriptive
   lifecycle slice.
2. Independently refine G05's exact observation selector: trace existing retained
   bindings, complete original request/result reconstruction requirements,
   version compatibility and no-write historical readback. Freeze one usable
   installed success/unknown/failure path and adversarial matrix before adding
   persistence. This is the next implementability investigation, not a promise
   that a production selector already exists.
3. Freeze G04/G06's working policy and permitted response destination only after
   the safety and observation requirements for that claim are available. G07's
   necessary-family/fundamental disposition and G08/G09 qualification remain
   explicit; do not import Future work.

Stop this discovery once each G03 category is reconciled, the present readiness
decision and alternatives are supported, and exact independent reviews and
documentation delivery finish. Do not expand it into all future contracts.

## Frozen documentation acceptance and effects

All eight Issue288 criteria are mandatory. Root owns exactly this Plan, Sprint50,
Plan61's status pointer, roadmap and upcoming overview. No runtime, dependency,
test, manifest, workflow or earlier frozen contract changes. Reviewers inspect
the complete clean committed diff and affected context independently, with no
candidate edits or nested delegation; each owns only a separate private report.

Adversarial claim matrix for inspection: selection versus eligibility;
listing-window versus listing-age; relative volume versus turnover/impact cost;
notice absence versus event-risk absence; public documentation versus source
admission; optional missing facts versus mandatory safety; future knowledge and
backdated acquisition; copied result versus typed retained observation; changed
candidate versus stale review; source-equivalent docs versus qualified runtime;
and planning delivery versus G03/product closure. Each must fail to support its
prohibited inference. Verification is prose/source inspection and exact
`git diff --check`, both complete independent R3 reviews and permitted lightweight
security/normal PR controls. No tests, heavy CI/CD, build or OCI publication.

Normal expected-head merge, ancestry-safe localmain, current Issue/Project/
milestone closeout and private retained receipts are required. The qualified
image remains Sprint49 code mainc7; this design does not requalify or relabel it.
All owner checkouts/worktrees and prior failures/evidence are preserved.

**Count:** G01/G02 closed; G03–G12 remain open, ten outcomes. This planning sprint
closes no behavior gap, changes no sprint estimate and does not finish any of the
eight signal-phase obligations. Future126/139/144/177/178, Windows and Issue250
remain separate. No actual provider/market/AI observation, profitability,
recommendation or whole-product readiness is claimed.
