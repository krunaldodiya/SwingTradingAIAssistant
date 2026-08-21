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
cardinalities, and evidence. They are not reinterpreted as instrument-agnostic.
Issue #125 / Plan 21 and the narrower Issue #127 adjusted-daily MVP are now
merged dependencies. [Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
orders tomorrow's separate Issue #130 working slices; they do not reopen or
reimplement Issue #127. New or migrated feature contracts must return typed
unsupported or insufficient evidence rather than embed an index-membership
check. Sprint 11 Market Regime v2 / PR #124 remains intentionally paused today.

Historical/backtest work is deferred, not deleted. It uses an explicit supplied
cohort and versioned OHLCV revision, makes no inferred historical index
membership claim, identifies `FIXED_COHORT_RETROSPECTIVE`, and discloses
selection/survivorship limits. Historical news, events, and sector inputs are
deferred/not-yet-evaluated, not permanently removed or silently neutral.

Every live fact is immutably archived from now with `published_at`, `known_at`,
source, revision, and affected identities. A per-feature/instrument/interval
ledger records only `AVAILABLE`, `NOT_PUBLISHED`, `NOT_RETAINED`, `SOURCE_GAP`,
`STALE`, `CONFLICTED`, or `UNLICENSED`. Coverage/windows are predeclared; no
later fact substitutes for unavailable history and unavailable dates are never
dropped.
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
| 11 | [#116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116) — Open/Todo; High priority/risk; Issue #125 and Issue #127 publication dependencies complete; PR #124 intentionally paused today | Current Market Regime v2 over admitted archived current facts, a successful provider-neutral corporate-action screen, and separate adjusted daily close facts. | [Plan 21](plans/21-current-supplied-cohort-corporate-action-screen-contract.md) merged through PR #128 as `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`. The Issue #127 `provider-neutral-adjusted-daily-close@v1-mvp` merged through [PR #129](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/129) as `c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`. Issue #130 remediation begins separately tomorrow and does not reimplement #127. PR #124 resumes only on explicit direction, consumes the then-applicable accepted contracts, preserves raw and adjusted evidence separately, exposes disagreement, and passes its own gates. | Historical/backtest implementation, generic adjustment engine, mixed-basis OHLC, Market Structure, signals, recommendations, entries/exits, position sizing, orders. |
| 12 | [#117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117) — Open/Todo; High priority/risk; not authorized to start before Sprint 11 closes | Current Sector Analysis and Sector Participation with immutable current sector snapshots. | Sprint 10 complete and Sprint 11 closed; approved current sector evidence/identity bindings; sector availability-ledger entries. | Historical taxonomy reconstruction/backfill, historical validation, recommendation, order. |
| 13 | [#118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118) — Todo; High priority/risk | Current news and event evidence with bounded fresh-input integration and immutable archive. | Current freshness/provenance/availability rules; no silent neutralization of absence. | Historical news/event backfill, historical validation, forecast, recommendation, order. |
| 14 | [#119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119) — Todo; High priority/risk | Integrated current packet binding price/volume, Market Regime, sector, news, events, and their archive identities for external-AI explainable research or `NO_TRADE`. | Exact Sprint 10–13 gates and current contracts. | Autonomous tool signal/recommendation, broker order, execution, historical-context substitution, claim of effectiveness. |
| 15 | [#120](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/120) — Todo; High priority/risk | Deferred fixed-cohort historical OHLCV store. | Current/live Sprints 10–14 usable; explicit cohort, versioned OHLCV revision, and predeclared coverage/windows. | Inferred index membership, historical news/event/sector neutralization, Market Structure, recommendation, order. |
| 16 | [#122](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/122) — Todo; High priority/risk | Capability-aware historical validation and pre-structure gate. | Sprint 15 store; study profile (`OHLCV_ONLY`, `OHLCV_PLUS_SECTOR`, or `OHLCV_PLUS_NEWS_EVENTS`); required availability-ledger entries; development/walk-forward/out-of-sample/untouched-test separation; identities and independent review. | Market Structure implementation, Price Action, Liquidity/SMC, recommendation, broker execution, guaranteed outcomes. |

Sprint 12 cannot start merely because Issues #125 and #127 are complete. The
remaining Sprint 11 gate is an explicitly resumed and accepted PR #124 Market
Regime v2 followed by Sprint 11 / Issue #116 review, merge, and closure.
Tomorrow's Issue #130 remediation neither closes Sprint 11 by itself nor
reopens completed Issues #125/#127.

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
completed Issues #125/#127 or interrupt Issue #130 remediation, PR #124,
Sprint 11, or WIP-one.

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
