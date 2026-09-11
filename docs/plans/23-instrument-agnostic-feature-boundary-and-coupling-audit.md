# Instrument-agnostic feature boundary and coupling audit

Status: **OWNER DECISION RECORDED / HISTORICAL AUDIT PRESERVED; CURRENT SUCCESSOR DELIVERY TRACKED IN ISSUE #172**

Tracking: [GitHub Issue #130](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/130)

Risk: **R2 documentation decision; later financial-research contract migrations retain their applicable R3 controls**

## Current migration crosswalk — September 11, 2026

The original audit and future-tense remediation rows below describe Issue
#130's baseline, not a claim that all successors remain unstarted. The accepted
current BharatStock capture and independent-fact work in #183/#184 was delivered
through PR #185. Issue [#172](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/172)
must reuse those delivered cores rather than restart the historical audit.
Its child [#186](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/186)
is in implementation; none of the following allocation claims that child or
the remaining public integrations are released.

| Existing authority | Disposition in the current dependency migration |
| --- | --- |
| Plan 02 request-minimal ingestion | Preserve the bounded ingestion/planning primitives. #186 acquires only its own two-completed-session requirement, not a default broad history. |
| Plan 04 public preview | Preserve its serialized contract and disclosure boundary. #186 adds a separately versioned public research result through the existing CLI; it does not widen old preview payloads. |
| Plan 06 current-month incremental data | Preserve its provisional and completed boundaries. #189 owns new cross-window refresh; #186's exact warm reuse is not labelled suffix-only incremental acquisition. |
| Plan 07 bounded Nifty 50 workflow | Preserve frozen named-universe behavior. #186's explicit symbol has no membership prerequisite and makes no index-eligibility claim. |
| Plan 19 supplied-cohort market data | Reuse canonical mapping, evidence and completed-session controls where compatible; preserve the old cohort/runtime identities. #186 does not reinterpret its input or output as a new supplied-cohort result. |
| Plan 20 Market Regime | Preserve the delivered core. #188 owns its supported independent price-context invocation; #186 does not manufacture a regime result. |
| Plan 21 corporate-action screen | Preserve nonexhaustive screen semantics and its qualified claims. The source-reported two-session fact does not claim that screen passed, nor make it a global prerequisite. |
| Plan 22 provider-neutral adjusted close | Preserve adjusted-close source/basis and predecessor readers. No BharatStock source-reported row is relabelled as qualified adjusted-close evidence. |
| Plan 23 instrument boundary | Reuse explicit canonical listed-equity admission and keep selection policy outside the feature. Preserve historical index-specific contracts rather than globally renaming them. |
| Plan 24 Sector Analysis | Preserve the delivered feature. #188 owns independent price context with its genuinely required classification evidence; classification is not a prerequisite for #186 Price Action. |
| Plan 25 Event Notice | Preserve source and nonexhaustive event scope. #187 owns integrated feature-local outcomes; absent event evidence does not fabricate or suppress an unrelated observed price fact. |
| Plan 27 composed evidence | #186 extracts/reuses the calendar-only composer and adds its canonical replay contract. Preserve the combined legacy acquisition and its historical claim scope. |
| Plan 30 capture-forward evidence | Reuse existing immutable BharatStock capture/reader and public fact builder. Preserve exact admitted predecessor V2 and pre-change V3 bytes; the new writer and borrowed root authority require their own verification. |
| Plan 31 Market Structure | Preserve its supported lookback and independent status. #187 composes it without imposing that lookback on two-session Price Action. |
| Plan 32 Price Action | Preserve frozen V1 input, basis and identity. #186 exposes the already delivered BharatStock two-session builder under a new public orchestration contract, not a relabelled V1 result. |
| Plan 33 efficient continuous capture | Reuse exact retained-evidence primitives. #189 owns changed-window/provisional behavior and #190 owns measured request, latency, retention and reuse evidence; no performance improvement is inferred from batching alone. |

This is a reuse/preserve/version/defer allocation, not an authorization to retire
historical readers or weaken source qualification, provider pauses, temporal
truthfulness, exact-byte review, CI or protected release controls.

## Owner decision

1. A reusable feature core accepts an explicit bounded list of canonical listed-equity instruments independently of index membership.
2. Point-in-time index membership, universe discovery, and default cohort selection are separate higher-level policies.
3. Product research, source qualification, validation, and default workflows focus on the point-in-time Nifty 50 plus Nifty Next 50: the Nifty 100.
4. An explicitly supplied supported listed stock outside those indices may use the same capability when canonical identity and every capability-specific evidence requirement exist. It is not the primary roadmap or validation focus.
5. Canonical identity is ISIN and exchange plus an effective symbol and versioned provider mappings. A current symbol, provider token, or index membership alone is not canonical identity.
6. Each feature declares its finite cohort bound and required data capabilities. Missing support returns a typed unsupported outcome; missing, stale, conflicting, or late required evidence returns insufficient evidence. Neither outcome may be replaced by an index check, omitted member, inferred value, or silent neutral.
7. Existing Nifty 50 V1 contract names, exact cardinalities, identities, and historical evidence remain truthful. Migration is incremental and versioned; current features are not represented as already generic.

This decision supersedes the product-scope conclusion in the 2026-08-09 Nifty 100 hypothesis note. That note remains unchanged historical evidence of the earlier open question.

### 2026-09-03 permanent owner clarification

The owner reaffirmed that Nifty 50, Nifty Next 50, Nifty 100, every sectoral
index, every Industry label, and every explicit watchlist are list-selection
policies rather than research implementations. The same reusable feature core
must accept the resulting exact canonical stock list. A supported stock must
not be rejected solely because it is outside a named index or category, and a
category name must not select a different calculation.

This does not authorize all Indian listings. The default product selection
remains Nifty 100; Nifty 500 is at most a carefully screened discovery ceiling,
not blanket admission. Every selected stock still passes separate objective,
versioned eligibility and evidence gates for sufficient listing/history,
canonical identity and mappings, data quality, liquidity/turnover, price
integrity, event risk, and the requested capability. Newly listed, very
small-cap, penny/very-low-priced, thinly traded, or otherwise
manipulation-susceptible stocks fail closed when those evidence-backed gates
are unsatisfied; price or capitalization alone does not prove manipulation.

The official [NSE Indices sectoral catalogue](https://www.niftyindices.com/indices/equity/sectoral-indices)
and [NSE sectoral-indices page](https://www.nseindia.com/static/products-services/indices-sectoral)
are concrete selection examples. Their Bank, Private Bank, PSU Bank, Financial
Services, Financial Services Ex-Bank, NBFC, Housing Finance, Insurance, and
MidSmall Financial Services lists overlap. The tool must preserve the exact
chosen source, as-of evidence, membership, and list identity rather than infer
one taxonomy or hard-code a Bank-analysis path.

Feature-specific finite limits are resource bounds, not category rules. A
larger list may be partitioned only when a versioned orchestrator preserves the
complete-list calculation and identity; independently calculated batch
verdicts must not be averaged or relabelled as a whole-list result.

## Non-goals

- No source, test, dependency, provider, data, schema, or runtime change in
  Issue #130's documentation slice.
- No reopening or reimplementation of the completed Issue #127 adjusted-daily
  MVP merged through PR #129.
- No Sprint 11 Market Regime v2 or PR #124 work today.
- No rewrite of frozen Plans 05, 10–17 or historical sprint records.
- No big-bang rename of `Nifty50*` types or removal of compatible historical readers.
- No generic multi-asset platform; no futures, options, forex, crypto, intraday trading, long-term advisory, broker order, autonomous recommendation, or guaranteed outcome.
- No claim that an instrument or feature is supported when canonical identity, provider mapping, required evidence, licence, freshness, or price basis is unavailable.
- No automatic qualification of every listed equity merely because a feature input can represent it.

## Target boundary

### Canonical listed-equity input

A future versioned canonical listed-equity record must bind, at minimum:

- ISIN;
- exchange and listed-equity segment/type;
- effective symbol and its effective interval;
- each required provider's provider ID, provider instrument identifier or symbol, mapping effective interval, and mapping-evidence identity; and
- immutable identity/provenance needed to prove that the mappings refer to the same listed equity at the invocation cutoff.

A feature request supplies a canonically ordered, unique list within that feature's declared maximum. There is no universal magic cardinality. The bound belongs to the feature contract and is challenged at the limit and limit-plus-one.

### Policy and capability composition

```text
point-in-time universe policy or explicit caller selection
  -> canonical listed-equity cohort
  -> capability admission for the requested feature
  -> provider-neutral feature core
  -> provider adapter or retained-evidence port
  -> fact, UNSUPPORTED_CAPABILITY, or INSUFFICIENT_EVIDENCE
```

The default universe policy selects point-in-time Nifty 50 plus Nifty Next 50. It owns membership evidence and the claim that a cohort is Nifty 100. A direct supplied-stock policy owns only caller selection and canonical identity; it makes no index-membership claim.

A provider adapter receives only already-admitted instruments and capability-specific requests. It must not import an index universe, decide membership, or turn an absent mapping into a different symbol. A feature core declares schedule, price basis, freshness, corporate-action, sector, news/event, or other evidence it actually requires and fails closed only for that declared profile.

## Sprint 1-to-current evidence audit

The audit read every available Sprint 1-through-current file: Sprint 1, Sprint 2 and its closeout, Sprint 3, Sprint 6, Sprint 8, Sprint 9, and Sprint 10. Sprints 4 and 5 have index entries but no standalone sprint files. No Sprint 7 or Sprint 11 sprint file is available; Sprint 11 is represented by the sprint index, upcoming-sprints overview, Issues #116/#125/#127, and Plans 21–22. Missing files are not reconstructed.

The plan audit covered every existing relevant file numbered 01–22. No Plan 20
file exists in `docs/plans`, so no Plan 20 content or conclusion is invented.

| Sprint evidence | Observed assumption and exact hotspots | Classification | Disposition |
| --- | --- | --- | --- |
| Sprint 1; Plans 01–02 | RELIANCE is the proof policy, while ingestion accepts a resolved `Instrument`; Plan 01 already makes ISIN the stable equity ID and treats symbols/provider keys as mappings. `market_data/instruments.py` and ingestion/storage contracts do not require index membership. | Legitimate narrow proof; reusable primitives already exist. | Preserve. Build the new canonical listed-equity contract from these proven identity rules rather than adding a second storage model. |
| Sprint 2; Plan 03 | One RELIANCE month, no multi-instrument or broader-universe claim. Production resolution must not hard-code symbol, ISIN, or provider key. | Legitimate operational qualification scope. | Preserve historical evidence unchanged. |
| Sprint 3; Plans 04–09 | Plan 04 correctly isolates RELIANCE in `PreviewAdmissionPolicyV1`. Plans 05 and 07 then make explicit-symbol download/read depend on an exact-50 `Nifty50UniverseSnapshotV1` and `Nifty50AdmissionPolicyV1`. `bounded_nifty50_workflow.py`, `nifty50_read_workflow.py`, `equity_admission.py`, and CLI selection bind reusable market-data operations to Nifty 50 membership. | Plan 05 is legitimate universe policy. Plan 07 and its source dependencies are reusable-core coupling. | Retain V1 contracts; add a new explicit canonical-equity path and keep Nifty 50/Nifty 100 selectors as composition policies. |
| Sprint 4; Plan 10 | The sealed 50 × 31 census, `nifty50-*` contracts, `stock_count == 50`, and membership reasons in `historical_evaluation/application.py`, `census.py`, and `contracts.py` describe one frozen experiment. | Legitimate historical experiment focus, not a reusable feature contract. | Do not rewrite. A future experiment uses a new contract and research-scope label. |
| Sprint 5; Plan 11 | Exactly 50 ISINs and global readiness only when all 50 rows are ready in `historical_evaluation/prospective_readiness.py`. | Legitimate frozen Nifty 50 evidence-qualification contract. | Do not generalize in place. Nifty Next 50 qualification needs a new policy/evidence version. |
| Sprint 6; Plans 12–13 | `nifty50-market-regime@v1` freezes 20 sessions, exact 50, and inclusive 30-of-50. `market_regime/facts.py`, `reducer.py`, `observed.py`, and `boundary.py` encode those exact semantics. | Legitimate frozen V1 product rule; not a reusable cohort core. | Preserve V1. Any supplied-cohort or Nifty 100 rule is a separately versioned contract with a cohort-scaled threshold and new validation. |
| Sprint 7 | No standalone sprint record or index entry was available. Current exact-50 Market Regime source is governed by Plans 12–13 and later Sprint 8 evidence. | Evidence gap; no reconstructed claim. | No historical edit. |
| Sprint 8; Plans 14–15 | `nifty50-sector-participation@v1` consumes `ResolvedNifty50UniverseSnapshotV1`, an exact-50 private handoff, fixed totals, and exact ISIN-set equality in `sector_analysis/participation.py` and `market_regime/observed.py`. | Legitimate published V1 semantics, but feature-core coupling for future reuse. | Preserve V1 and add a new version only after the upstream reusable Market Regime/cohort handoff exists. |
| Sprint 9; Plans 16–17 | Acquisition evidence is scoped to frozen Nifty 50 Layer B and exact sorted 50-ISIN manifests. The terminal result is blocked and grants no authority. | Legitimate index-specific evidence-acquisition decision. | Preserve unchanged; it is not the reusable-core migration path. |
| Sprint 10; Plan 19 | `CurrentSuppliedCohortManifestV1` is bounded and canonical, and `CurrentSuppliedCohortAdmissionPolicyV1` admits listed equities by ISIN/symbol. The service still calls `CurrentCohortUniverseResolverPortV1`; default `RetainedCurrentNifty50UniverseResolverV1` makes every supplied member occur in a Nifty 50 snapshot. `daily_ohlcv.py`, `intraday_views.py`, `public_coverage.py`, and `public_query.py` also branch on `Nifty50AdmissionPolicyV1`. | Mixed: reusable identity/fact core plus membership coupling in service/read composition. | Separate capability admission from universe policy without changing Plan 19 V1 replay or names. |
| Sprint 11 current state; Plans 21–22 | Plan 21 consumes the Plan 19 cohort and merged through PR #128 at `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`. The completed Issue #127 MVP merged through PR #129 at `c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`; its adjusted-close service accepts explicit 1–50 `(isin, project_symbol, provider_symbol)` rows and has no direct index lookup, but its input remains `plan19_cohort`, lacks exchange/effective-symbol mapping, and is composed through the Nifty 50 Plan-19 path. PR #124 / Sprint 11 v2 remains paused today. | Delivered narrow capability with contract/type coupling and incomplete canonical identity; not instrument-agnostic. | First Issue #130 remediation target tomorrow. Version the input/mapping boundary, preserve the delivered MVP behavior, keep Nifty 100 selection above it, and do not reopen or reimplement Issue #127. |

## Cross-cutting source classification

### Legitimate universe and workflow policy

- `market_data/universe_snapshot.py`: exact point-in-time Nifty 50 evidence and replay.
- `market_data/current_cohort.py::RetainedCurrentNifty50UniverseResolverV1`: a valid Nifty 50 policy adapter, but not a universal feature prerequisite.
- Plans 05, 10–13, 16–17 and their historical-evaluation source: deliberately Nifty 50-specific evidence or experiments.
- Existing CLI `--universe nifty50-current`: a named selector, not a feature-core identity rule.

### Reusable primitives to retain

- `market_data/instruments.py::Instrument` and instrument snapshots: ISIN/security identity with provider aliases.
- Request planning, rate limiting, storage, schedule validation, canonical candles, daily/intraday derivation, archive, and provider ports where they consume an injected equity admission policy.
- `CurrentSuppliedCohortManifestV1` canonical ordering/bounds and `CurrentSuppliedCohortAdmissionPolicyV1` exact ISIN/symbol admission, subject to a new complete exchange/effective-symbol identity version.
- `market_data/adjusted_daily/yfinance_adapter.py`: provider detail behind the adjusted-close port; it should remain unaware of index membership.

### Reusable-core coupling to remove incrementally

- `market_data/bounded_nifty50_workflow.py` and `nifty50_read_workflow.py`: explicit lists still require Nifty 50 universe resolution and Nifty-specific request/report types.
- `market_data/equity_admission.py` plus type branches in `daily_ohlcv.py`, `intraday_views.py`, `public_coverage.py`, and `public_query.py`: behavior depends on concrete `Nifty50AdmissionPolicyV1` instead of the declared equity-admission protocol.
- `market_data/current_cohort.py::CurrentCohortMarketDataServiceV1`: capability evaluation and index-cohort verification occur in the same service pass.
- `market_data/current_corporate_action_screen.py`: reusable screening consumes Plan 19-specific cohort types.
- `market_data/adjusted_daily/service.py`: reusable adjusted close consumes `plan19_cohort`, caps at literal 50, and lacks complete canonical listed-equity mapping fields.
- `market_regime/*` and `sector_analysis/participation.py`: exact-50 rules are correct for frozen V1 but cannot be called reusable for another bounded cohort.
- `market_data/cli.py` and `runtime_identity_manifest.py`: composition and code-identity inventories must follow each versioned migration without aliases or parallel hidden paths.

## Exact contracts and modules affected by future work

| Boundary | Existing contract/module | Required future change |
| --- | --- | --- |
| Canonical equity identity | Plan 01 identity rules; `Instrument`; instrument snapshot contracts | Add one versioned listed-equity identity/mapping contract with ISIN, exchange, effective symbol, provider mappings, mapping evidence, cutoff, and finite bounds. Reuse existing storage identity; do not create a second candle identity. |
| Universe policy | Plan 05; `Nifty50UniverseSnapshotV1`; `Nifty50UniverseStoreV1` | Retain as Nifty 50 V1. Add point-in-time Nifty Next 50/Nifty 100 policy evidence separately; explicit supplied-stock policy makes no index claim. |
| Current price/volume | Plan 19; `current_cohort.py`; `daily_ohlcv.py`; `public_coverage.py`; `public_query.py`; `intraday_views.py` | Version the reusable capability input, remove index verification from the feature service, and compose Nifty 100 or explicit-stock policy above it. Eliminate concrete-policy type branches. |
| Adjusted daily close | Plan 22; `market_data/adjusted_daily/service.py`; `yfinance_adapter.py` | Version `plan19_cohort`/mapped-member input to complete canonical identity; keep provider selection, price basis, schedule, whole-result failure, and no-fallback rules. |
| Corporate-action screen | Plan 21; `current_corporate_action_screen.py` | Accept the versioned canonical equity cohort and capability-specific retained observations; keep index policy outside and preserve nonexhaustive-screen semantics. |
| Download/coverage/query | Plans 04 and 07; `equity_admission.py`; `bounded_nifty50_workflow.py`; `nifty50_read_workflow.py`; CLI | Add explicit canonical-equity workflow contracts, retain named Nifty selectors as policy adapters, and keep historical V1 serialization readable. |
| Market Regime | Plans 12–13; `market_regime/boundary.py`, `facts.py`, `reducer.py`, `observed.py` | Preserve exact-50 V1. Define a new supplied-cohort version only with an explicit finite bound, inclusive cohort-scaled threshold, capability profile, and fresh validation protocol. Do not alter V1 identities. |
| Sector Participation | Plans 14–15; `sector_analysis/participation.py` | Preserve V1. New version consumes the new Market Regime handoff plus independently supplied point-in-time classification evidence for the identical cohort. |
| Historical evaluation | Plans 10–11 and 16–18; `historical_evaluation/*` | Frozen experiments remain. Later Sprint 15/16 profiles may adopt canonical cohorts through new versions; no current historical result is relabelled. |

## Tomorrow's ordered smallest working vertical slices

Each slice must be separately tracked, test-first where it changes behavior, and complete through its focused runtime proof before the next slice. No slice may claim Nifty 100 readiness without point-in-time Nifty Next 50 evidence.

1. **Adjusted-close explicit-stock successor vertical.** Build a separately versioned successor to the delivered Issue #127 MVP input boundary; do not reopen or reimplement `provider-neutral-adjusted-daily-close@v1-mvp`. Add the complete canonical listed-equity identity, exercise one supplied synthetic listed equity through request admission, the existing injected adjusted-close capability, normalization, public result, and typed unsupported/insufficient failures without a universe resolver, then compose the unchanged current Nifty 50 policy above it. Preserve the merged provider, adjusted-basis, schedule, raw-separation, and failure behavior.
2. **Current completed-daily explicit-stock vertical.** Extract capability evaluation from `CurrentCohortMarketDataServiceV1` so one canonical supplied equity with retained identity and daily evidence can produce the existing kind of bounded fact without Nifty membership. Keep a separate Nifty 50 policy wrapper and prove it still rejects a nonmember when the workflow claims Nifty 50.
3. **Nifty 100 default-policy vertical.** Add a versioned higher-level selector that composes separate point-in-time Nifty 50 and Nifty Next 50 evidence, proves disjoint ISIN sets and effective/cutoff validity, and emits one bounded canonical cohort. Until both evidence sets exist, return insufficient evidence; never substitute a current list.
4. **Corporate-action screen vertical.** Migrate Plan 21's reusable screen to the canonical cohort input, prove one supplied outside-default equity follows the same retained-observation path, and retain its nonexhaustive coverage limitation and whole-result failure semantics.
5. **Download/coverage/query explicit-list vertical.** Add an index-independent explicit-equity path over the existing ingestion/read cores, remove concrete `Nifty50AdmissionPolicyV1` branches in favor of the existing protocol, and retain `--universe nifty50-current` plus a future Nifty 100 selector only as composition policies.
6. **Market Regime and Sector Analysis new versions.** After the active Sprint 11 dependency order permits it, define and implement a separately versioned bounded-cohort Market Regime with an inclusive 60% rule and a matching Sector Participation handoff. Preserve `nifty50-market-regime@v1` and `nifty50-sector-participation@v1` unchanged. This slice must not be folded into PR #124 without its own accepted contract and evidence.
7. **Historical-profile migration only when Sprints 15–16 activate.** Reuse the canonical cohort and capability ledger in new historical contract versions; preserve every frozen census/readiness/acquisition result and its original scope label.

## Completion conditions for the remediation program

- A feature core imports no Nifty universe resolver or concrete Nifty admission class.
- The default Nifty 100 policy and direct supplied-stock policy can call the same feature contract.
- Provider adapters receive canonical admitted mappings and contain no index-membership logic.
- Every migrated feature states its own cohort bound and capability profile and distinguishes malformed input, unsupported capability, insufficient evidence, and success.
- Existing V1 canonical bytes, identities, stored evidence, and historical readers remain supported for their recorded scope until a separately approved retirement decision.
- Documentation and runtime names do not claim generic support before the matching behavioral proof passes.

## Documentation-only evidence and limits

Issue #130 inspected governing documentation, every available Sprint 1-through-current record, relevant Plans 01–22, the research-vision/instrument-extensibility note, the Nifty 100 hypothesis note, and current source hotspots. This plan records a static coupling audit only. It does not prove runtime behavior, data availability, provider support, Nifty Next 50 point-in-time evidence, or completion of any remediation slice.
