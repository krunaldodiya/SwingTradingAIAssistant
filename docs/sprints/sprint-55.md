# Sprint 55: automated supported signal decisions

Live status is owned by [Issue #299](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/299),
Milestone 47, and the Delivery Project. [Plan 70](../plans/70-automated-supported-signal-decisions.md)
defines this R3 financial-research, provider-provenance, and credential-bound
Sprint. Owner and risk owner: Krunal Dodiya. Base main:
`9183bf4b82d4163935ad862c4774ea996eadb4dd`.

## Goal

Deliver a versioned automated decision path for one retained `CURRENT_STRUCTURE`
NSE-equity observation or admitted observation pair. A human CLI user and an AI
harness receive the same source-bound result: an eligibility decision, a bounded
causal `RESEARCH_CANDIDATE` / `NO_TRADE` / `UNKNOWN` decision, and an ordered
ledger explaining why each decisive rule passed, failed, or could not be trusted.

## Frozen delivery scope

The V3 path reads only immutable observation handles and automatically performs
at most four serial provider reads: one exact-identity Upstox V3 quote, bounded
BharatStock identity/history reads, and one strict Upstox corporate-action read.
It applies fixed price, circuit, book, history, turnover, and corporate-action
safety gates before the retained causal policy. Each ledger row names its rule,
outcome, reason code, plain-language explanation, source identities, and
comparison measurements. It never emits credentials, raw provider payloads,
private paths, or full bars.

The provider contract accepts documented one-through-five-level quote books and
uses the best valid bid/ask pair. Exact Decimal comparisons decide fixed circuit,
spread, and turnover thresholds so a rounded displayed quotient cannot turn a
below-threshold fact into a pass.

## Explicit boundary

This Sprint is a research-candidate policy. It does not place orders, rank a
stock list, call an AI model, predict returns, set targets or position sizes,
operate a broker, persist provider data, or assess existing holdings. A real
provider-backed qualification is required before any source-qualified Stage 2
or G08 claim; absent normal environment credential injection is a qualification
limit, never a reason for manual data staging or credential handoff.

## Delivery evidence

The final exact candidate requires independent functional/domain and
security/privacy/provenance review, hosted public-repository quality and
installed-distribution gates, merge/main admission, private package publication,
live tracker closeout, and worktree cleanup. The retained closeout receipt must
separately state the status of real-provider qualification.
