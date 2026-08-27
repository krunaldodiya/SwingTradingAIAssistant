# Sprint 14 — Current supplied-cohort research packet

Status: **IN PROGRESS — TWO PR #140 P2 BLOCKERS FIXED; ALL REQUIRED CURRENT SMOKES AND ALL EXACT-CURRENT LOCAL GATES PASSED (852 FOCUSED; 3,400 FULL AT 89.53% COVERAGE; RUFF FORMAT/CHECK 275, PYRIGHT 0/0, VULTURE 80, DIFF, BUILD, WHEEL, CLEAN INSTALLED-WHEEL IMPORTS/RUNTIME); COMMIT, EXACT REVIEWS, PUSH/HOSTED/MERGE/CLOSEOUT PENDING; NO COMPLETION/DELIVERY**

- Issue: [#119 — Sprint 14: integrated current research packet](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119) — **Open**
- Active plan: [Plan 27 — Current same-pass Market Regime contract](../plans/27-current-same-pass-market-regime-contract.md)
- Superseded WIP: [Plan 26 — Packet `@v1`](../plans/26-current-supplied-cohort-research-packet-contract.md) — **will not ship**
- Risk: **R3 / High — financial, temporal, and evidence impact**
- Exact-current local gates: **ALL PASSED** — Ruff format/check over 275 files, Pyright 0/0, Vulture 80, `git diff --check`, `uv build` sdist+wheel, and clean installed-wheel imports/runtime checks.
- Official acquisition automation: **IMPLEMENTED — current exact schedule, mapping, Industry, event, raw, and Plan-21 evidence retained and validated**.
- Fresh post-close evidence: **PASSED** with schedule SHA-256 `f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`, Industry SHA-256 `1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`, and Event SHA-256 `fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
- Event publisher compatibility: **IMPLEMENTED — current range filename and exact UTF-8 bytes with or without BOM; legacy filename/manual licence remains BOM-only replay compatibility**.
- Composed schedule cutover: **IMPLEMENTED — schema v3; `nse-upstox-composed-calendar`; source-manifest-bound release; no authoritative-calendar relabel**.
- Plan-27 cohort bridge mappings: **IMPLEMENTED**; adjusted `NOT_ATTEMPTED` / `UPSTREAM_INSUFFICIENT_EVIDENCE` truthfully suppresses Plan-22 after upstream raw or screen insufficiency.
- Ten review blockers: **FIXED LOCALLY WITHOUT A NEW SUBSYSTEM** — both PR #140 P2 blockers (active-date partial canonical/mapping validity and schema-specific Industry/Packet URL attribution); late completion-marker retry guards; zero-redirect enforcement; restored global `ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day month-start acquisition; pre-Plan-22 deadline enforcement; corrected Plan-24 wording.
- Current-source positive smokes: **PASSED SEPARATELY** — the strict one-lease post-close `RELIANCE` positive and mandatory Aug-27 market-hours `RELIANCE` positive both passed; neither substitutes for the other.
- Genuine current-byte IRCTC exact `NO_TRADE` negative: **PASSED with exact insufficiency ledger and guarded retry/original-time preservation**.
- Exact-current Vulture/diff/build/wheel and clean installed-wheel gates: **PASSED**.
- Commit, exact-current reviews, push, hosted checks, merge, and closeout: **PENDING**.
- Acceptance, completion, and delivery: **NOT CLAIMED**.
- Historical WIP evidence: **Plan-26 packet `@v1` had 101 focused tests pass with `--no-cov`; not transferable to the successor**.

The final 14-file focused portfolio passed **852 tests** with `--no-cov`. On
these current bytes, the strict one-lease post-close `RELIANCE` positive passed
for the 2026-08-26 decision session: 21 raw bars; Market Regime, Industry, and
Packet `OBSERVED`; partial `NOT_APPLICABLE`; Plan 21 `SCREENED`; Plan 22
`SUCCESS`; and guarded retries preserved exact bytes, identities, and original
times.

The mandatory Aug-27 market-hours `RELIANCE` positive passed on frozen
fingerprint
`61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`
during the actual active session. The decision cutoff was
`2026-08-27T04:29:06.612060Z` (`09:59:06` IST), and the effect deadline was
`2026-08-27T04:28:36.612060Z`. Composed schedule SHA-256
`fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae`
defined 2026-08-27 as `REGULAR`, 09:15–15:30 IST, with S0 2026-07-29 and S20
2026-08-26; the 2026-08-27 mapping observation was
`02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3`.

Raw was 21/21 `OBSERVED`; Plan 21 was `SCREENED`; live Plan 22 was `SUCCESS`
before the deadline; Market Data, Market Regime, Industry, and Packet were
`OBSERVED`; Event was `RETAINED`. Packet identity SHA-256 was
`cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474`,
and context identity SHA-256 was
`e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a`.
The requested partial was truthfully `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows, separately labelled
`PARTIAL_CURRENT_SESSION`, excluded from the completed grid and Market Regime,
nonfatal, and never substituted. Exact retries preserved bytes, identities, and
original times and caused zero effects; source remained unchanged and all
resources were closed.

PR #140's two P2 blockers are fixed on the exact current uncommitted 66-path
set. Active-session partial acquisition now requires canonical identity and an
effective provider mapping valid on the active date before any partial query;
expired canonical or mapping validity performs zero partial queries. Industry V2
preserves the schema-specific legacy/current source URL and Packet attribution.

The mandatory Aug-27 market-hours `RELIANCE` positive rerun **PASSED** on exact
current uncommitted 66-path fingerprint
`3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e` at cutoff
`2026-08-27T08:18:59Z`. Raw, Market Regime, Industry, and Packet were
`OBSERVED`; Plan 21 was `SCREENED`; Plan 22 was `SUCCESS`. Active-date canonical
and mapping validity passed before the partial path returned `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows. Industry and Packet retained the current
`nsearchives.nseindia.com` URL attribution. Exact retries preserved bytes,
identities, and original times and caused zero provider effects. The prior
post-close positive, earlier Aug-27 market-hours positive, genuine IRCTC
negative, and exact 66-path set remain preserved.

The exact-current full suite passed **3,400 tests at 89.53% total coverage**
against the **87%** threshold, and the 14-file focused portfolio passed 852 tests.
All exact-current local gates pass: Ruff format/check over 275 files, Pyright 0/0,
Vulture at 80%, `git diff --check`, `uv build` producing sdist and wheel, and clean
installed-wheel imports/runtime checks. Installed runtime identities are raw
`8d99ebe8781d48d6a45a331878ff3a730bd23237c152e5837797c003c71d047b`,
Industry V2 `e8e4c5408afe49e4f99484c0ab8a23cc897dfb3a34b84d00f7230405e7d93f29`,
Market Regime V3 `74928b2b190e0e676ebb88fd4df5ae3d3856edaf8a08694da325393543a3542a`,
and Packet V2 `a36e3f42a773f0d533dcfbc3726b83c800028bdf9f11bcae299e176eb020a4ea`.
Commit, exact-current reviews, push, hosted checks, merge, and closeout remain
pending. No acceptance, completion, or delivery is claimed.

The directory-edge `st_nlink` portability fix remains in place without
weakening leaf metadata checks; exact source-file checks remain enforced and
the dependent runtime identity manifests remain current.

Owner platform boundary: the native supported target is POSIX-style macOS and
Linux with identical evidence guarantees. Native Windows is unsupported and not
claimed; Windows users use Linux through WSL2 or Docker. Exact-candidate Linux
hosted CI has not run and is not claimed.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass; commit, exact-current reviews, push, hosted checks, merge, and closeout remain pending. No acceptance, completion, or delivery is claimed until the lifecycle is complete.

## Goal

Deliver the owner-authorized current-only same-pass successor: exact approved
raw bars available now for the latest 21 completed official sessions, retained
now with truthful current `known_at`; Market Regime V3; same-pass Industry
Participation V2; and one owner-private local Research Packet V2.

Current availability does not depend on the tool having run on prior sessions.
The schedule derives `decision_session` as the latest official session whose
`close_at <= decision_cutoff`: during market hours it is the prior completed
session; after today's official close it may be today. Missing Plan-20
prospective objects is never a current failure. An optional separately labelled
`PARTIAL_CURRENT_SESSION` supplies provisional current price/volume context only.

The deterministic tool supplies facts and provenance only. It does not claim
historical availability, replay/backtest evidence, intraday trading authority,
signal, recommendation, position size, order, or effectiveness.

## FIRST_WORKING_SLICE

- explicit exact `1..50` canonical NSE `EQUITY` cohort independent of index
  membership;
- one bounded UTC `decision_cutoff` after invocation and authoritative
  latest-completed-session resolution; no after-close-only or
  `IST_DATE(cutoff)` invariant;
- exact `S0..S20`, where `S20` is the resolved latest completed official
  session and S0 is exactly 20 official sessions earlier;
- exact `UPSTOX` / `RAW` completed daily grid from approved retained/provider
  evidence available now, with actual current receipts and `known_at`;
- identical current packet for 0-, 1-, 7-, and 30-day inactivity when all
  current admitted inputs are equal; no prior-run/prospective-envelope reason;
- optional `PARTIAL_CURRENT_SESSION` status/projection, never used as a
  completed fact, Market Regime/Industry input, historical claim, signal, or
  recommendation; missing/conflicting partial is non-fatal to valid completed
  components;
- exact Plan-21 screened corporate-action and Plan-22 V2 adjusted S0/S20
  comparability, with raw/adjusted member-direction equality;
- `current-supplied-cohort-market-regime@v3` aggregate plus archive-minted
  private handoff consumed only by
  `current-supplied-cohort-industry-participation@v2`;
- clean replacement of unpublished packet `@v1` by
  `current-supplied-cohort-research-packet@v2`, with no alias or dual path;
- exact four-row component/source ledger, separately labelled partial packet
  projection, whole-result insufficiency for required-component failures, and
  mandatory `INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED`;
- immutable context and packet retain-before-return under real
  `StorageRootLease` values, completion-marker logical commits, structural
  bounds, redaction, and byte-identical exact retry; and
- owner-private local Python only; no CLI, API, MCP, UI, public transport,
  provider fallback, broker call, or real-money action.

## LATER_IMPROVEMENTS

- historical availability ledgers, replay, backtest, backfill, revised-source
  lineage, and correction graphs;
- capture-first Design B, generalized persistence/registries, measured parallel
  acquisition, BSE, another provider, or provider fallback;
- full Plan-22 hardening, external attestation, or a generalized threat model;
- recurring polling/systematic history, official Sector taxonomy, general news,
  attachments, sentiment, materiality, ranking, or scoring;
- API, MCP, CLI, UI, notification, hosted/shared/public delivery, or another
  model-transfer boundary;
- Market Structure; and
- signals, recommendations, position sizing, orders, or effectiveness claims.

The scope-expansion circuit breaker applies. A later item becomes a blocker only
when review cites a violated current acceptance condition or concrete current
safety, correctness, usability, authorization, privacy, or evidence-integrity
failure.

## Accepted module decision

1. **Expected value:** current Market Regime and packet availability without waiting 21 future sessions or requiring prior tool runs.
2. **Scope fit:** current-only canonical NSE equities, 21 completed daily raw sessions, optional provisional partial context, delivered Industry/events, and owner-private local Python consumption.
3. **Material data/research risk:** historical-availability mislabelling and cohort/schedule/mapping/source/price-basis or partial/completed splicing.
4. **Smallest alternative:** one retained same-pass context reusing Plan-21/22/24/25 instead of replay, another provider, or another delivery surface.
5. **Decision:** **ACCEPTED — Design A**, under [Plan 27](../plans/27-current-same-pass-market-regime-contract.md).

This decision adds only the owner-authorized bounded current acquisition edge
and truthful composed schedule source. It adds no additional provider,
polling, signal, order, or historical claim. Plan-21/22/24/25 owner-private
source-use boundaries remain authoritative as amended.

## R3 controls and acceptance

R3 applies for financial, temporal, and evidence impact. R4 does not apply
because this slice claims no execution or financial advice and performs no
destructive action. Before completion the exact candidate must provide:

- RED tests for current availability independent of 0/1/7/30-day inactivity,
  authoritative latest-completed-session resolution in market-hours and
  finalized post-close modes, exact 21-session grids, current `known_at`, and
  absence of any prospective-envelope dependency/reason;
- RED tests for every optional partial state and identity, non-fatal
  missing/conflicting partial, and fail-closed `PARTIAL_AS_COMPLETE`;
- exact cohort/mapping/schedule/source identities, Plan-21/22 comparability,
  reason order/suppression, private handoff, Industry reconciliation, packet
  clean cutover, redaction, bounds, retention, tamper failure, and retry;
- one real market-hours `OBSERVED` context/Industry/packet smoke with prior
  completed S20 and explicit partial semantics; a second finalized post-close
  mode should prove today's S20 and partial `NOT_APPLICABLE`, with an unavailable
  second mode recorded as a limit rather than claimed;
- one separate genuine current retained insufficiency smoke proving mandatory
  `NO_TRADE`; missing prior Plan-20 envelopes or tool inactivity is not a valid
  negative capability;
- independent functional/domain/temporal and security/privacy/provenance review;
- focused tests and full repository format, lint, type, dead-code, coverage,
  diff, build, installed-wheel, and hosted gates; and
- exact-SHA review, merge, and truthful lifecycle closeout.

The smokes prove current freshness, temporal integrity, cross-component binding,
immutable retention, reproducibility, and consumer disposition only. They
cannot prove historical availability, source completeness, strategy quality,
recommendation quality, intraday trading, or effectiveness.

## Consumer boundary

Only a verified retained Packet V2 is AI-consumable. An observed packet permits
facts-only contextual research over completed S20 close/volume, aggregate Market
Regime, aggregate Industry, retained event notices, and the separately labelled
optional partial status/projection. The partial is provisional and cannot
replace completed facts or become a Market Regime/Industry input, historical
claim, signal, recommendation, or order.

An insufficient packet has all five AI fact fields null and requires
`INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED`; the consumer cannot override
reasons, recompute facts, infer missing values, fetch attachments/general news,
or use knowledge after the cutoff.

NSE-derived source narrative, event-notice material, and Industry material must
not be sent to a hosted, third-party, public, shared, or multi-user model or
service without separate owner authorization and source-use review. Stronger
producer authentication and external attestation remain deferred.

## Current lifecycle evidence

Issue #119 is open. Plan 27 is active and Sprint 14 is **IN PROGRESS — ALL
TWO PR #140 P2 BLOCKERS FIXED; ALL REQUIRED CURRENT SMOKES AND ALL
EXACT-CURRENT LOCAL GATES PASSED (852 FOCUSED; 3,400 FULL AT 89.53%
COVERAGE; RUFF FORMAT/CHECK 275, PYRIGHT 0/0, VULTURE 80, DIFF, BUILD, WHEEL,
CLEAN INSTALLED-WHEEL IMPORTS/RUNTIME); COMMIT, EXACT REVIEWS,
PUSH/HOSTED/MERGE/CLOSEOUT PENDING; NO COMPLETION/DELIVERY** after operational evidence
showed zero usable Plan-20 21-object prospective inputs and the owner selected
the current same-pass correction.

Plan-26 packet `@v1` was unpublished WIP and is superseded before delivery. Its
101 focused-test result remains historical WIP/repair evidence only.

The final 14-file focused portfolio passed **852 tests** with `--no-cov`; the
exact current source full suite passed **3,400 tests at 89.53% total coverage**
against the **87%** threshold. Ruff format/lint and Pyright currently pass. Final
Vulture/diff/build/wheel rerun remains pending, as do commit, exact-current
reviews, push, hosted checks, merge, and closeout. Prior candidate Vulture, diff,
build, and installed-wheel evidence remains historical only.

Ten review blockers are fixed locally without a new subsystem: the two PR #140
P2 fixes for active-date partial canonical/mapping validity and schema-specific
Industry/Packet URL attribution; late
completion-marker retry guards; zero-redirect enforcement; restored global
`ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate
kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day
month-start acquisition; pre-Plan-22 deadline enforcement; and corrected
Plan-24 wording.

The directory-edge `st_nlink` portability fix remains in place without
weakening leaf metadata checks; exact source-file checks remain enforced and
the dependent runtime identity manifests remain current. Plan-27 cohort bridge
mappings remain implemented, including truthful Plan-22 suppression after
upstream raw or screen insufficiency.

Owner platform boundary: the native supported target is POSIX-style macOS and
Linux with identical evidence guarantees. Native Windows is unsupported and not
claimed; Windows users use Linux through WSL2 or Docker. Exact-candidate Linux
hosted CI has not run and is not claimed.

Official acquisition automation retained and validated the current exact
schedule, mapping, Industry, event, raw, and Plan-21 evidence. Fresh post-close
evidence passed with schedule SHA-256
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`,
Industry SHA-256
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`,
and Event SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
The strict one-lease post-close `RELIANCE` positive passed with 21 raw bars;
Market Regime, Industry, and Packet `OBSERVED`; partial `NOT_APPLICABLE`; Plan
21 `SCREENED`; Plan 22 `SUCCESS`; and guarded retries preserving exact bytes,
identities, and original times.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass; commit, exact-current reviews, push, hosted checks, merge, and closeout remain pending. No acceptance, completion, or delivery is claimed until the lifecycle is complete.

## Changed and nonchanged boundaries

Plan 27 freezes this exact current WIP implementation file set:

```text
src/swing_trading_ai_assistant/market_data/http.py
src/swing_trading_ai_assistant/market_data/download_preparation.py
src/swing_trading_ai_assistant/market_data/open_month.py
src/swing_trading_ai_assistant/market_data/provisional_validation.py
src/swing_trading_ai_assistant/market_data/current_evidence_acquisition.py
src/swing_trading_ai_assistant/market_data/current_evidence_acquisition_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/current_event_notice.py
src/swing_trading_ai_assistant/market_data/current_industry_classification.py
src/swing_trading_ai_assistant/market_data/current_corporate_action_screen.py
src/swing_trading_ai_assistant/market_data/current_corporate_action_screen_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/adjusted_daily/service.py
src/swing_trading_ai_assistant/market_data/current_same_pass_daily.py
src/swing_trading_ai_assistant/market_data/current_same_pass_daily_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py
src/swing_trading_ai_assistant/market_data/schedule_evidence.py
src/swing_trading_ai_assistant/market_data/current_event_notice_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/current_industry_classification_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v3.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v3_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_v2_runtime_identity_manifest.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_v2.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_v2_runtime_identity_manifest.py
src/swing_trading_ai_assistant/sector_analysis/current_industry_participation_runtime_identity_manifest.py
src/swing_trading_ai_assistant/research_packet/__init__.py
src/swing_trading_ai_assistant/research_packet/current_supplied_cohort.py
src/swing_trading_ai_assistant/research_packet/current_supplied_cohort_runtime_identity_manifest.py
tests/market_data/test_current_evidence_acquisition.py
tests/market_data/test_open_month.py
tests/market_data/test_provisional_validation.py
tests/market_data/test_public_preview_preparation.py
tests/market_data/test_current_event_notice.py
tests/market_data/test_current_industry_classification.py
tests/market_data/test_current_corporate_action_screen.py
tests/market_data/test_adjusted_daily_close_v2.py
tests/test_sprint3_release_readiness.py
tests/market_data/test_current_same_pass_daily.py
tests/market_data/data/plan27_raw_v1_configuration_preimage.json
tests/market_data/data/plan27_raw_v1_schema_preimage.json
tests/market_regime/test_current_supplied_cohort_v3.py
tests/market_regime/test_current_supplied_cohort_v2.py
tests/market_regime/test_current_supplied_cohort.py
tests/sector_analysis/test_current_industry_participation_v2.py
tests/sector_analysis/test_current_industry_participation.py
tests/research_packet/test_current_research_packet.py
tests/market_regime/data/plan27_v3_schema_preimage.json
tests/sector_analysis/data/plan27_industry_v2_schema_preimage.json
tests/research_packet/data/plan27_packet_v2_schema_preimage.json
docs/plans/27-current-same-pass-market-regime-contract.md
docs/plans/21-current-supplied-cohort-corporate-action-screen-contract.md
docs/plans/22-provider-neutral-adjusted-daily-close-contract.md
docs/plans/24-current-supplied-cohort-sector-analysis-contract.md
docs/plans/25-current-supplied-cohort-event-notice-contract.md
docs/plans/26-current-supplied-cohort-research-packet-contract.md
docs/architecture-freeze-v1.md
docs/roadmap.md
docs/upcoming_sprints_overview.md
docs/sprints/sprint-12.md
docs/sprints/sprint-14.md
docs/sprints/README.md
README.md
AGENTS.md
docs/herdr-multi-agent-workflow.md
```

This is the identical current 66-path Plan-27 WIP set: production, tests and
schema fixtures, governing/lifecycle records, and workflow records are kept in
the same order as Plan 27.

The current blocker repair makes bounded affirmative changes to the listed
acquisition, Plan-21/22/24/25 integration, tests, manifests, and contract
records. It does not claim those components are unchanged. The shared verifier
preserves no-follow traversal and exact regular-file/named-directory-edge
binding; the global manifest is inventory regeneration. The packet import
contract is exactly
`swing_trading_ai_assistant.research_packet.current_supplied_cohort`; its
package `__init__.py` marker remains intentionally empty and exports nothing.
No dependency, lockfile, workflow,
provider selection, Plan-20 V1/V2, CLI, API, MCP, UI, historical/backtest,
signal, recommendation, or order surface changes.
