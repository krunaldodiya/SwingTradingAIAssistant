# Upcoming Sprints Overview

This document records the owner-level **current/live/realtime first** dependency
status and remaining sequence. Completed lifecycle claims below are tied to
their linked Issues and pull requests; future rows are a minimum dependency
plan, not authorization, delivery promise, acquisition plan, or publication
claim. Each remaining sprint requires its own accepted contract, focused
evidence, exact reviewed revision, and applicable repository/hosted gates.
Failed or insufficient evidence requires a replacement sprint rather than
automatic progression.

## Shared lane rule

Current/live/realtime work starts with current supplied-cohort price/volume,
then current Market Regime, Sector Analysis, news/events, and an integrated
current packet. The product-default selection policy focuses on the
point-in-time Nifty 50 plus Nifty Next 50; a reusable feature receives only the
explicit bounded canonical listed-equity cohort selected above it. The
deterministic tool supplies facts only; an external AI may produce explainable
research or `NO_TRADE`, never a tool-invented autonomous signal,
recommendation, position size, entry/exit, or order.

Index membership and feature capability are separate gates. Membership evidence
is required when the workflow claims a Nifty 50, Nifty Next 50, or combined
Nifty 100 cohort. Feature admission instead requires canonical ISIN/exchange
identity, effective symbol and provider mappings, plus that feature's declared
data capabilities. An explicitly supplied supported listed stock outside the
Nifty 100 may use the same feature when those requirements are met; it does not
become part of the default research or validation universe.

Existing Sprint 1–10 and frozen V1 records keep their original Nifty 50 names,
cardinalities, and evidence. They are historical exact-50 records, not
instrument-agnostic claims. Issues #125, #127, and
[#132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132) are
merged Sprint-11 dependencies.
[Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
owns separate future migrations; it does not reopen those dependencies or
reinterpret frozen evidence. Sprint 11
[#116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116) is
closed/completed after
[PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
merged the V2 comparability semantics.

Historical/backtest work is deferred, not deleted. It uses an explicit supplied
cohort and versioned OHLCV revision, makes no inferred historical index
membership claim, identifies `FIXED_COHORT_RETROSPECTIVE`, and discloses
selection/survivorship limits. Historical news, events, and sector inputs are
deferred/not-yet-evaluated, not permanently removed or silently neutral.

Every admitted live fact is immutably archived from now with required
`known_at`, source, revision, affected identities, and the publisher
publication/effective fields actually supplied by that feature's admitted
source. An unavailable publisher field remains explicit null/unavailable
provenance; acquisition time is never relabelled as publisher time. A
per-feature/instrument/interval ledger records only `AVAILABLE`,
`NOT_PUBLISHED`, `NOT_RETAINED`, `SOURCE_GAP`, `STALE`, `CONFLICTED`, or
`UNLICENSED`. Coverage/windows are predeclared; no later fact substitutes for
unavailable history and unavailable dates are never dropped.
Point-in-time backtests and forward tests use only evidence available by their
historical cutoff. An unavailable factor is explicitly unavailable/not applied;
it is never fabricated or backfilled from later evidence, and it does not block
unrelated available-feature research. The current/live contract may instead
require a factor as a whole-result gate for the specific claim it makes.

This is sequencing only. Sprint 15 remains the historical store and Sprint 16
remains the historical validation/pre-structure gate. Their retained scope
includes point-in-time membership, sector, corporate-action, and source
provenance plus point-in-time availability ledgers; historical backtests with
look-ahead, survivorship, selection, and data-snooping controls; separated
in-sample, walk-forward, out-of-sample, and untouched-test regions;
forward/paper testing; and realistic costs and slippage. Missing historical
evidence remains an explicit unavailable
state at the cutoff and is neither fabricated nor treated as neutral. No
initially planned capability is removed by the current/live-first order.

Provider routing is capability-based, explicit, and provenance-bound. Upstox is
primary for current/live raw OHLCV and the Plan-21 corporate-action screen.
yfinance is first only for the separate Plan-22 adjusted daily close; every fact
records provider and price basis, and no provider is a generic silent fallback.
Angel One is deferred as a future qualified adapter and is not implemented now.
yfinance offers long daily history but only the latest 60 days of intraday data;
it is an unofficial personal/research-use Yahoo client whose retrospective
adjustments may be revised and are not strict point-in-time authority.

Raw Upstox OHLCV remains unchanged. A yfinance adjusted close never fills an
Upstox candle. Any later Market Structure calculation must use a complete raw
OHLC series or a complete adjusted OHLC series consistently, never mixed bases.


| Sprint | Tracker and lifecycle | Atomic outcome | Minimum dependency and gate | Explicit non-goals |
| --- | --- | --- | --- | --- |
| 10 | [#121](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/121) — Closed/completed; High priority/risk | Current supplied-cohort `market-data` foundation: bounded current price/volume facts for 1–50 Nifty 50 identities and immutable archive records. | Canonical cohort identity/selection SHA; retained instrument resolution; latest completed daily OHLCV and optional `PARTIAL_CURRENT_SESSION`; provenance/availability ledger; whole-cohort insufficiency; no effect before admission. | Historical/backtest implementation, Market Regime, sectors, news/events, signals, recommendations, entries/exits, position sizing, orders. |
| 11 | [#116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116) — Closed/completed; High priority/risk | Current Market Regime V2 comparability over admitted archived current facts, a successful provider-neutral corporate-action screen, and separate adjusted daily close facts. | Issues [#125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125), [#127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127), and [#132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132) merged. [PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124) merged reviewed head `d56120fb5966dffea32207b59f1edf0673b2e51b` as `f03edf3690e34e25a57b58a15450129e3bf9a5e9`; 296 focused / 2,867 full / 91.03%, Ruff/Pyright/Vulture/build, sealed no-network and live current-prospective smokes, hosted Quality/build, and GitGuardian passed. | Historical/backtest implementation, generic adjustment engine, mixed-basis OHLC, Market Structure, signals, recommendations, entries/exits, position sizing, orders. |
| 12 | [#117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117) — Open/**IN PROGRESS — RECEIPT-PERSISTED CANDIDATE LOCALLY VERIFIED; FRESH EXACT-SHA REVIEW AND DELIVERY PENDING**; High priority/risk | Current exact supplied-cohort Industry classification and deterministic aggregate Industry Participation from one operator-acquired official NSE Indices Nifty 100 CSV. | Sprint 10 complete and Sprint 11 closed; [Plan 24](plans/24-current-supplied-cohort-sector-analysis-contract.md) owns the exact contract. All earlier repair-round reviews and gate evidence are superseded trace. The seventh repair persists and reconstructs the deterministic canonical retained receipt across a process retry and rejects missing, corrupt, or spliced receipts. Focused verification passed 105 tests; full local gates passed 2,982 tests at 90.82% coverage plus Ruff format/check, Pyright, Vulture 80, and build. The unchanged 100-row / 6,610-byte official parser smoke is provenance only. Fresh exact-SHA review and delivery remain pending; the exact reviewed SHA will be recorded externally after review. | Automated acquisition, alternate sources, official Sector taxonomy, historical classification, and broker order placement. |
| 13 | [#118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118) — Todo; High priority/risk | Current news and event evidence with bounded fresh-input integration and immutable archive. | Current freshness/provenance/availability rules; no silent neutralization of absence. | Historical news/event backfill, historical validation, forecast, recommendation, order. |
| 14 | [#119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119) — Todo; High priority/risk | Integrated current packet binding price/volume, Market Regime, sector, news, events, and their archive identities for external-AI explainable research or `NO_TRADE`. | Exact Sprint 10–13 gates and current contracts. | Autonomous tool signal/recommendation, broker order, execution, historical-context substitution, claim of effectiveness. |
| 15 | [#120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120) — Todo; High priority/risk | Deferred fixed-cohort historical OHLCV store. | Current/live Sprints 10–14 usable; explicit cohort, versioned OHLCV revision, and predeclared coverage/windows. | Inferred index membership, historical news/event/sector neutralization, Market Structure, recommendation, order. |
| 16 | [#122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122) — Todo; High priority/risk | Capability-aware historical validation and pre-structure gate. | Sprint 15 store; study profile (`OHLCV_ONLY`, `OHLCV_PLUS_SECTOR`, or `OHLCV_PLUS_NEWS_EVENTS`); required availability-ledger entries; development/walk-forward/out-of-sample/untouched-test separation; identities and independent review. | Market Structure implementation, Price Action, Liquidity/SMC, recommendation, broker execution, guaranteed outcomes. |

Sprint 11 is closed after all three dependencies and PR #124 merged. Sprint 12 /
Issue #117 is **IN PROGRESS — RECEIPT-PERSISTED CANDIDATE LOCALLY VERIFIED;
FRESH EXACT-SHA REVIEW AND DELIVERY PENDING** under Plan 24.

The prior exact-SHA R3 review returned `REQUEST_CHANGES` / `FAIL` for missing
deterministic receipt persistence/recovery and stale lifecycle records. All
earlier repair-round reviews and gate evidence are superseded trace. The seventh
repair persists a deterministic canonical retained receipt with `known_at`, all
required identities, and exact private rows, reconstructs the original retained
evidence across a process retry, and rejects missing, corrupt, or spliced
receipts. Focused verification passed 105 tests. Full local gates passed 2,982
tests at 90.82% coverage, Ruff format/check, Pyright, Vulture 80, and build.

The unchanged official parser smoke admitted the exact current 100-row,
6,610-byte artifact with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`
under classification schema
`7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`;
it is parser provenance only, not live participation or effectiveness evidence.
Fresh exact-SHA independent quality `APPROVE` and security `PASS` and delivery
remain pending. The exact reviewed SHA will be recorded externally after review;
this lifecycle record contains no self-referential candidate SHA. Pull request,
hosted CI/GitGuardian, merge, and Issue closure remain pending.

## Market Structure boundary

Market Structure is **earliest Sprint 17** and is not specified or started by
this overview. Sprint 16 returns only `APPROVED_TO_START_MARKET_STRUCTURE` or
`BLOCKED` with exact reasons; failure adds a replacement sprint. This is a gate,
not a promise. Any later Market Structure contract must choose one complete raw
OHLC basis or one complete adjusted OHLC basis for its whole window; a yfinance
adjusted close cannot be mixed with Upstox raw open/high/low values.

## Future packaging outside current WIP

[Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
is future low-priority work for a standalone `swing-trading-market-data` PyPI
distribution while the full application remains installable. Both distributions
must consume one authoritative market-data codebase with no copied provider
logic. This packaging outcome is not part of Sprints 11–16 and must not reopen
completed Issues #125/#127/#132 or Sprint 11, alter future Plan-23 migrations,
or alter active Sprint 12 scope.

## Deferred and superseded historical records

Issue #121 is closed/completed and supplies the current foundation. Issues #111 and #115 are **closed /
not planned** with no published implementation. Plans 12 and 17 retain their
original evidence and conclusions as historical records; deferred Plan 18 is
linked to #120/#122. None are declared wrong at the time.

The former contemplated official-inquiry content SHA-256
`a2d762cd93dfca56d5623e260816c1aee0a6ae2a9a400097cc6f2d51c77f6412` and
authorization-payload SHA-256
`84797b9c424aa6da36d46b1b516f3cbe08d8205801d296953a5edf474d2ffe85` were
revoked before send. No inquiry email, provider contact, provider call,
credential use, or acquisition occurred. These are not Plan 11's historical
public-page research receipt hashes.
