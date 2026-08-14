
  Owner-approved product-direction and brainstorming handoff

  Please preserve these decisions in durable project memory, audit the entire repository and Linear for earlier Codex-era versions, and reconcile the appropriate documentation. Treat the
  statements below as owner-approved direction, while maintaining a strict distinction between current implementation scope and future architectural extensibility.

  1. Current product scope

  The currently supported product remains:

  - Point-in-time research and analysis for Nifty 50 equity stocks.
  - The primary use case is swing trading.
  - The preferred holding horizon is approximately 5–10 trading days, with justified variation around that range.
  - NO_TRADE, insufficient evidence, missing data, and no qualifying signal remain legitimate first-class outcomes.
  - The tool must not weaken selection, evidence, liquidity, or risk thresholds merely to produce a trade.
  - It remains a research and decision-support tool, not an autonomous trading bot.
  - It must not place broker orders or imply guaranteed returns.

  Do not interpret the architectural decisions below as authorization to expand the current implementation scope immediately.

  2. Long-term segment direction

  The long-term architectural focus is now limited to:

  - Equities
  - Futures and options (F&O)

  Explicitly remove the following from current and future product direction:

  - Crypto
  - Forex

  This supersedes any earlier discussion or memory that treated forex or crypto as possible future research segments.

  ### Current versus future boundary

  - Equity—particularly Nifty 50 equity swing research—is the only currently active product scope.
  - F&O is a future scalability consideration, not an approved current implementation.
  - Do not add F&O data sources, workflows, contracts, dependencies, UI, APIs, or roadmap delivery work without a separately approved epic/specification.
  - Existing documentation that excludes F&O from current implementation should remain operationally true.
  - Documentation may clarify that the exclusion is a current delivery boundary, not necessarily a permanent architectural prohibition.
  - Index analysis may be useful as equity-market context and may later support approved equity/F&O research, but this does not authorize index trading or derivatives implementation now.

  3. Architectural scalability principle

  Adopt this principle:

  │ Keep the research architecture appropriately extensible for equities and future F&O where correctness permits, while enforcing Nifty 50 equity swing research as the current product
  │ admission boundary.

  The system should avoid unnecessary coupling to:

  - one symbol universe;
  - one equity index;
  - one broker/vendor;
  - one instrument identifier format;
  - one exchange segment;
  - equity-only terminology inside genuinely reusable research contracts;
  - one specific holding horizon where a generic contract can safely express it.

  However, do not create speculative abstractions or over-engineer current modules merely to claim future F&O support. Preserve extensibility only where it is natural, testable, and does
  not weaken current correctness.

  Future F&O support cannot be achieved merely by passing a derivative symbol into an equity workflow. It would require separately designed and approved contracts for matters such as:

  - underlying and derivative instrument identity;
  - futures expiry and rollover;
  - option type, strike and expiry;
  - lot sizes and tick sizes;
  - point-in-time contract availability;
  - settlement and exercise;
  - margin and leverage;
  - open interest and derivative liquidity;
  - continuous-series construction;
  - contract roll rules;
  - transaction costs and slippage;
  - gap and expiry risk;
  - position and portfolio risk semantics;
  - backtest fill assumptions;
  - provenance and vendor authority.

  Do not implement these now. Only avoid needless architectural decisions that would permanently prevent them.

  4. Preferred swing horizon

  Record that the current research focus preferably targets approximately:

  - 5–10 trading days of holding time, more or less when justified by the setup and evidence.

  This should become an explicit research-horizon direction if it is not already documented.

  Do not turn 5–10 days into an unsupported guaranteed exit rule. A future strategy/setup contract must precisely define:

  - intended horizon;
  - maximum holding period, if any;
  - invalidation and exit rules;
  - calendar-day versus trading-day interpretation;
  - handling of holidays and gaps;
  - how horizon affects evaluation and backtesting.

  5. Primary and fallback equity universes

  The intended future universe policy is hierarchical:

  1. Screen and research the Nifty 50 first.
  2. Apply the approved signal, evidence, liquidity, and risk thresholds without relaxation.
  3. If no Nifty 50 candidate qualifies, preserve NO_TRADE as valid.
  4. A future approved workflow may then screen Nifty Next 50 as a secondary fallback universe.
  5. Never lower thresholds simply to produce a trade.
  6. Results must identify the source universe explicitly.
  7. Do not silently replace this policy with an always-combined Nifty 100 scan.

  The rationale is that Nifty 50 may be too narrow to produce qualifying swing opportunities on many days. A conditional Nifty Next 50 fallback could expand the opportunity set while
  keeping Nifty 50 primary.

  This is a future research direction, not immediate implementation authorization.

  ### Before approving the fallback

  A future research/specification task should define and validate:

  - the exact deterministic meaning of “no good Nifty 50 signal”;
  - whether fallback occurs only when there are zero qualifying candidates or also when portfolio constraints eliminate them;
  - unchanged minimum signal/evidence/risk/liquidity thresholds;
  - point-in-time Nifty Next 50 membership;
  - point-in-time sector classification;
  - symbol-change and corporate-action handling;
  - data availability and quality;
  - liquidity and slippage differences;
  - provider and storage impact;
  - candidate-ranking behavior across universes;
  - whether Nifty 50 and Next 50 results remain separately ranked;
  - prevention of survivorship and look-ahead bias;
  - out-of-sample opportunity frequency;
  - quality versus quantity of additional candidates;
  - concentration and portfolio effects;
  - operational cost.

  Compare at least:

  - Nifty 50 only;
  - conditional Nifty Next 50 fallback;
  - optionally Nifty 100 as a research comparison, not an assumed production policy.

  The fallback should be adopted only if evidence shows that it improves useful opportunity coverage without degrading quality or research integrity.

  6. Check prior Codex-era universe decisions

  Search the complete repository, Git history where useful, durable memory, and Linear for:

  - Nifty Next 50
  - Next 50
  - Nifty 100
  - broader universe
  - universe fallback
  - secondary universe
  - opportunity frequency
  - no qualifying signal
  - no good signal
  - ARK-101
  - any related Codex discussion or planning artifacts

  The retained context suggests that ARK-101 may contain a Nifty 100 hypothesis, possibly deferred or excluded. Verify its actual current state and description rather than assuming.

  Determine whether the owner’s earlier concern was:

  - fully preserved;
  - partially preserved;
  - reduced to a hypothesis ticket;
  - contradicted by current documentation;
  - or lost.

  Do not duplicate an existing Linear issue. Update an appropriate existing issue if it already owns the future-universe hypothesis; otherwise create a narrowly scoped future
  research/documentation issue only after confirming no duplicate exists.

  7. Price Action and SMC reference repositories

  The owner has supplied multiple reference codebases containing Price Action and Smart Money Concepts logic.

  These repositories are:

  - strictly read-only;
  - used only to understand ideas, terminology, logic, and possible research concepts;
  - never to be modified;
  - never to be copied or pasted into this project;
  - not authoritative specifications;
  - not evidence that any concept is valid.

  Any feature adopted into this product must be:

  - independently evaluated;
  - independently specified;
  - implemented from scratch;
  - deterministic where possible;
  - point-in-time safe;
  - testable and falsifiable;
  - reproducible;
  - protected against look-ahead and data-snooping bias;
  - validated out of sample or through walk-forward analysis;
  - documented with concept provenance.

  Do not adopt “SMC” as one opaque strategy package. Evaluate its individual concepts separately, potentially including:

  - market structure;
  - swing highs and lows;
  - break of structure;
  - change of character;
  - liquidity sweeps;
  - displacement;
  - fair-value gaps or imbalances;
  - order blocks;
  - supply and demand zones;
  - premium/discount regions;
  - support and resistance;
  - candle structure;
  - trend and range regimes.

  Subjective or unfalsifiable concepts may be rejected. Concepts requiring retrospective visual discretion must not be presented as deterministic facts unless converted into precise,
  testable definitions.

  The deterministic tool should own:

  - calculations;
  - timestamps;
  - point-in-time market facts;
  - feature derivation;
  - validation;
  - provenance;
  - backtesting.

  The consuming AI may contextualize supplied facts but must not invent missing structures or recompute market facts from raw OHLC.

  8. Audit the reference documentation

  Inspect at least:

  - docs/reference-repositories.md
  - docs/architecture-freeze-v1.md
  - docs/roadmap.md
  - relevant feature/module specifications
  - AGENTS.md
  - README and product-scope language
  - universe contracts and plans
  - Git history for earlier Codex edits
  - related Linear issues

  Determine whether Price Action and SMC repositories are already:

  - listed;
  - described as read-only;
  - mapped to concrete concepts;
  - accompanied by provenance expectations;
  - constrained against copying;
  - or merely named without useful categorization.

  If the current documentation is insufficient, update it minimally so that it clearly states:

  - references are read-only idea sources;
  - adopted concepts require independent specification and implementation;
  - source provenance must be recorded;
  - no referenced implementation is copied;
  - concept validity is not presumed.

  Do not invent repository descriptions without inspecting them.

  9. Documentation reconciliation requested by the owner

  After auditing existing evidence, update appropriate durable documentation where necessary. Likely candidates include:

  ### AGENTS.md

  Clarify:

  - current scope remains Nifty 50 equity swing research;
  - preferred holding horizon is around 5–10 trading days;
  - current exclusions remain enforceable;
  - future architectural consideration is limited to equity and F&O;
  - forex and crypto are excluded from current and future direction;
  - future F&O implementation requires separate approval;
  - a future Nifty Next 50 fallback does not change current Nifty 50-only delivery.

  Do not weaken the active scope guardrails.

  ### docs/architecture-freeze-v1.md

  If compatible with its ownership and freeze rules, clarify:

  - reusable research contracts should avoid unnecessary segment coupling;
  - equity and future F&O are the only intended segment families;
  - current modules remain Nifty 50 equity-specific where domain correctness requires it;
  - speculative abstractions are prohibited;
  - future F&O needs dedicated domain contracts rather than reused equity assumptions;
  - forex and crypto are outside architectural direction.

  Because this is an architecture-governance document, follow the repository’s required evaluation and approval process. Surface conflicts rather than silently editing frozen decisions.

  ### docs/roadmap.md

  Record as future research—not active Sprint 4 commitment unless separately approved:

  - preferred 5–10 trading-day swing horizon;
  - Nifty 50 as primary universe;
  - conditional Nifty Next 50 fallback hypothesis;
  - unchanged qualification thresholds;
  - NO_TRADE remains valid;
  - F&O extensibility as a future epic-level possibility;
  - forex and crypto excluded.

  Do not turn brainstorming into scheduled delivery without owner approval at the appropriate epic boundary.

  ### Universe specifications

  Ensure future extensibility can preserve:

  - explicit universe identity;
  - point-in-time membership;
  - point-in-time sector evidence;
  - separate primary/fallback labels;
  - no silent current-list historical backfill;
  - no implicit Nifty 100 combination;
  - reproducible selection order.

  Do not implement Next 50 support under the current issue unless explicitly authorized.

  ### docs/reference-repositories.md

  Clarify the read-only Price Action/SMC research role and independently implemented concept policy.

  ### Research or strategy specifications

  Where appropriate, record:

  - current 5–10 trading-day preferred horizon;
  - deterministic feature ownership;
  - AI/tool boundary;
  - NO_TRADE;
  - future universe fallback research;
  - concept-by-concept Price Action/SMC evaluation.

  10. Memory requirements

  Create or update durable project memory with a concise owner-approved record covering:

  - Nifty 50 equity swing research is the current supported product.
  - Preferred holding horizon is approximately 5–10 trading days, with justified variation.
  - Future segment direction is equity and F&O only.
  - F&O is not currently authorized; it is an architectural scalability consideration.
  - Forex and crypto are completely excluded.
  - Supersede or remove prior memory suggesting future forex or crypto support.
  - Nifty 50 remains the primary universe.
  - Nifty Next 50 is a future conditional fallback hypothesis only when no Nifty 50 candidate meets unchanged thresholds.
  - Never weaken thresholds to force a trade.
  - NO_TRADE remains valid before and after fallback consideration.
  - Price Action/SMC repositories are read-only study sources.
  - Any adopted Price Action/SMC concept must be independently specified, implemented from scratch, point-in-time safe, and evidence-tested.

  Avoid saving speculative implementation detail as settled architecture.

  11. Linear handling

  Linear remains the sole agile tracker, not a substitute for durable product documentation or memory.

  Before creating anything:

  1. Search existing issues, particularly ARK-101 and related universe/research tickets.
  2. Determine whether an existing issue already owns:
      - broader universe research;
      - Nifty Next 50/Nifty 100 evaluation;
      - Price Action/SMC concept inventory;
      - product-scope documentation reconciliation.
  3. Update an existing issue if appropriate.
  4. Create a new issue only if there is real, nonduplicative work.
  5. Do not mark future F&O or Next 50 work as active implementation without owner approval.

  A documentation-reconciliation issue may be appropriate if current work does not already cover these owner decisions, but it should not be mixed into an unrelated release repair.

  12. Current Sprint sequencing

  Do not let this brainstorming derail the current release work.

  Maintain the agreed sequence:

  1. Finish and seal Sprint 3 reconciliation.
  2. Complete ARK-149 governance/document status reconciliation.
  3. Implement and validate ARK-150’s measured TDD feedback-loop optimization.
  4. Complete the active post-Codex foundation goal.
  5. Then conduct formal owner-facing Sprint 4 brainstorming and planning.

  These product-direction decisions should be preserved now, but new Price Action, SMC, Next 50, or F&O production implementation must not begin prematurely.

  13. Provisional Sprint 4 subjects to revisit

  Once the foundation gate is complete, include these in structured Sprint 4 brainstorming:

  - explicit swing research/setup contract;
  - 5–10 trading-day horizon semantics;
  - deterministic Price Action feature definitions;
  - concept-by-concept SMC evaluation;
  - trend, momentum, volatility, volume, liquidity, and relative-strength factors;
  - index and sector regime context for equity research;
  - explainable candidate scoring;
  - NO_TRADE and insufficient-evidence behavior;
  - deterministic risk and invalidation facts;
  - realistic backtesting and walk-forward validation;
  - next-executable-bar fills, costs and slippage;
  - structured facts for AI consumption;
  - future Nifty Next 50 fallback research;
  - long-term equity/F&O architectural seams.

  This is a brainstorming inventory, not an approved Sprint 4 commitment.

  14. Required output from the main coordinator

  Please report back with:

  1. What was already documented.
  2. What earlier Codex decisions were found.
  3. Any conflicts between these owner decisions and existing architecture/scope documents.
  4. Which durable memories were created, updated or superseded.
  5. Which documentation files require changes.
  6. Which exact changes were made and why.
  7. Whether an existing Linear issue covers the work.
  8. Any new or updated Linear issue, with duplicate checks.
  9. Which items remain future hypotheses rather than current commitments.
  10. Confirmation that forex and crypto have been removed from future direction.
  11. Confirmation that current Nifty 50 equity scope was not accidentally weakened.
  12. Confirmation that no unrelated Sprint