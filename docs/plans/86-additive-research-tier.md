# Plan 86: additive research-tier policy

Status: accepted bounded specification under [Issue #445](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/445). Owner and risk owner: Krunal Dodiya. Risk tier: R3 — high: user-visible research qualification, financial-adjacent policy, and daily reporting. Base: `6ceca31819cf1f7dc7aa52cd4c2de60b55965428` (`main`, 2026-11-25).

## Authority and boundary

The owner directed on 2026-11-25 that the tool remain a swing-trading research/analysis instrument and that only relative, objectively useful features be included. The retrospective candidate audit (private ledger entry `2026-11-25-candidate-return-audit.md`) found that the strict `swing-analysis-policy@v1` rejected several later winners, concentrated in `VOLUME_EXPANSION`, `WEEKLY_TREND_UP` and `CANDLE_BODY_QUALITY`.

This Plan adds a **separate** research watchlist. It does not change the strict `QUALIFIED` finalist policy, the scan decision, BOS detection, safety gates, entry/exit semantics, or any execution surface. The new tier is explicitly `PROVISIONAL_RESEARCH`; it is not a buy list, target, recommendation, or validated strategy.

## Outcome

- Every analyzed candidate carries an additive `research_tier` object.
- The object separates hard structural/risk gates from soft style confidence.
- A risk-distance ceiling is part of the hard gates.
- The daily pass report and private ledger show the tier and its flags.
- The existing `swing-analysis@v2` facts and `swing-analysis-policy@v1` outcome remain byte-for-byte unchanged.

## Existing policy (unchanged)

`swing-analysis-policy@v1` keeps its eight gates and outcome logic:

- `ATR_AVAILABLE`
- `VOLUME_EXPANSION` (>=1.50x prior 20-session average)
- `CANDLE_BODY_QUALITY` (bullish body >=60%)
- `RETEST_CONFIRMED`
- `WEEKLY_TREND_UP` (UPTREND)
- `DEMAND_ZONE_VALID`
- `EXTENSION_WITHIN_2_ATR`
- `RISK_POSITIVE`

Its `QUALIFIED`, `WATCH`, `NOT_QUALIFIED` and `INSUFFICIENT` outcomes are not changed by this Plan.

## New research-tier contract

Schema: `swing-analysis-research-tier@v1`. Mode: `PROVISIONAL_RESEARCH`.

Per member:

```json
{
  "schema": "swing-analysis-research-tier@v1",
  "mode": "PROVISIONAL_RESEARCH",
  "tier": "RESEARCH_WATCH",
  "hard_gates": [
    {"id": "ATR_AVAILABLE", "kind": "CRITICAL", "status": "PASS", "observed": "5.87", "requirement": "atr20 present"},
    {"id": "EXTENSION_WITHIN_2_ATR", "kind": "CRITICAL", "status": "PASS", "observed": "0.71", "requirement": "<=2.00 ATR"},
    {"id": "RISK_POSITIVE", "kind": "CRITICAL", "status": "PASS", "observed": "3.06", "requirement": "close above structural stop"},
    {"id": "RISK_WITHIN_3_5_ATR", "kind": "CRITICAL", "status": "PASS", "observed": "3.06", "requirement": "<=3.50 ATR"},
    {"id": "RETEST_CONFIRMED", "kind": "STRUCTURAL", "status": "PENDING", "observed": "TESTING", "requirement": "state != BELOW_LEVEL"},
    {"id": "DEMAND_ZONE_VALID", "kind": "STRUCTURAL", "status": "PASS", "observed": {}, "requirement": "zone available and close >= zone low"}
  ],
  "soft_gates": [
    {"id": "VOLUME_EXPANSION", "strength": "MODERATE", "observed": "1.25", "requirement": "prior-median ratio >=1.50 strong, >=1.00 moderate"},
    {"id": "WEEKLY_TREND_UP", "strength": "MODERATE", "observed": "RANGE_OR_TRANSITION", "requirement": "UPTREND strong; RANGE above 20-week average moderate"},
    {"id": "CANDLE_BODY_QUALITY", "strength": "STRONG", "observed": {"direction": "BULLISH", "body_percent": "97.03"}, "requirement": ">=60 strong, 40-60 moderate"}
  ],
  "weak_soft_gates": [],
  "flags": ["VOLUME_EXPANSION_MODERATE", "WEEKLY_TREND_UP_MODERATE", "CANDLE_BODY_QUALITY_STRONG", "RETEST_CONFIRMED_PENDING"]
}
```

At the document level:

```json
{
  "schema": "swing-analysis-research-tier@v1",
  "mode": "PROVISIONAL_RESEARCH",
  "tier_counts": {
    "RESEARCH_QUALIFIED": 0,
    "RESEARCH_WATCH": 3,
    "NOT_QUALIFIED": 2,
    "INSUFFICIENT": 0
  }
}
```

### Blocking gates

Critical gates:

1. `ATR_AVAILABLE`
2. `EXTENSION_WITHIN_2_ATR`
3. `RISK_POSITIVE`
4. `RISK_WITHIN_3_5_ATR` — `risk_atr <= 3.50`

A critical gate that is unavailable or pending makes the member `INSUFFICIENT`; a critical gate that fails makes it `NOT_QUALIFIED`.

Structural gates:

5. `RETEST_CONFIRMED`
6. `DEMAND_ZONE_VALID`

A structural gate that explicitly **fails** (`BELOW_LEVEL` or close below the demand zone) makes the member `NOT_QUALIFIED`. A **pending** or unavailable structural gate is a flag, not a blocker. Fresh breakouts frequently show `RETEST_CONFIRMED = TESTING`; BANKBARODA's audit case had a pending retest and still ran +17%. Treating pending retest as `INSUFFICIENT` would recreate the over-filtering this slice is meant to address.

The 3.5 ATR ceiling is a calibration hypothesis from the audit: the three best risk/reward misses (BANKBARODA 3.06, UNIONBANK 2.22, BSE 2.87) were inside 3.5; the low-risk/reward movers (BHARTIARTL 4.60, LT 4.20, AXISBANK 6.80, TVSMOTOR 4.67, GMRAIRPORT 5.73) were outside. It is not validated.

### Soft gates and strength

A soft gate is `STRONG`, `MODERATE`, `WEAK`, or `UNAVAILABLE`. `UNAVAILABLE` is treated as weak and adds a flag.

Volume:

- Compute `median_ratio = event_volume / prior_median`.
- `STRONG` if >=1.50; `MODERATE` if >=1.00; otherwise `WEAK`.
- Missing/zero median -> `UNAVAILABLE`.

Weekly:

- `STRONG` if `trend == UPTREND`.
- `MODERATE` if `trend == RANGE_OR_TRANSITION` and `above_twenty_week_average is true`.
- Otherwise `WEAK` (including `DOWNTREND` or range below the 20-week average).

Candle:

- `STRONG` if bullish and body >=60%.
- `MODERATE` if bullish and body >=40%.
- Otherwise `WEAK` (bearish or body <40%).

### Tier logic

- Any critical gate unavailable or pending -> `INSUFFICIENT`.
- Any critical gate fail, or any structural gate fail -> `NOT_QUALIFIED`.
- No blocking failure, and all three soft gates `STRONG` -> `RESEARCH_QUALIFIED`.
- No blocking failure, and at most one soft gate `WEAK` -> `RESEARCH_WATCH`.
- No blocking failure, and two or more soft gates `WEAK` -> `NOT_QUALIFIED`.

Pending or unavailable structural gates carry flags such as `RETEST_CONFIRMED_PENDING` or `DEMAND_ZONE_VALID_UNAVAILABLE`.

`RESEARCH_QUALIFIED` is a research-tier label, not the existing `QUALIFIED` finalist outcome. The report must show both labels distinctly.

## Integration

### Analysis artifact

- `swing_analysis._analyze_member` sets `member["research_tier"]` after the existing policy.
- `_unavailable_member` sets a tier object with `INSUFFICIENT` and the relevant unavailable gate.
- `analyze_scan` sets the document-level `research_tier` summary next to `policy`.
- `analysis_identity_sha256` includes the new object; identities change, which is expected for the additive contract.

### CLI

Add to `swing-analysis`:

```sh
swing-analysis --research-tier \
  --analysis-json /absolute/analysis-2026-11-23.json \
  --output json
```

Reads an existing `swing-analysis@v2` document. No provider access. It requires a valid `report_identity_sha256` (canonical document integrity; an unkeyed checksum, not a signature), emits `swing-analysis-research-tier-report@v1` with ordered members, tier counts, flags, the raw source-document SHA-256 and the verification status. It recomputes every tier from member facts and never trusts a precomputed `member.research_tier` label. `--output table` is also available and prints a `PROVISIONAL_RESEARCH — not strict QUALIFIED` banner. The normal `--scan-json` mode is unchanged.

### Daily report and ledger

- `scripts/pass_report.py` adds a **Research watchlist** section listing `RESEARCH_WATCH` and `RESEARCH_QUALIFIED` members with their flags; the existing candidate table keeps the strict policy outcome. It recomputes the tier from facts.
- `scripts/write_scan_ledger_entry.py` adds a `- Research tier ...` line and the soft/hard flags under each candidate. It recomputes the tier from facts.
- `gate_friction_report.py` remains unchanged; it is a strict-policy diagnostic.

## Compatibility

- `swing-analysis@v2` and `swing-analysis-policy@v1` gain no field changes; the new object is additive.
- Existing consumers that ignore unknown keys continue to work.
- The daily report/ledger changes are additive sections/lines.
- No registry, storage, provider, or portfolio contract changes.

## Security and privacy

- No new provider calls, credentials, or storage.
- The tier is computed only from the existing analysis facts; precomputed tier labels and forged source identities are not trusted.
- Input numerics are bounded. Volume median ratios must be positive and at most 100; candle bodies must be 0–100; a malformed value becomes `UNAVAILABLE`, never the top research tier.
- The analysis identity check is document integrity, not a cryptographic signature; the owner-private file remains the trust boundary.
- No raw bars, private paths, account data, or broker payloads are introduced.
- The output carries no target prices, returns, position sizes, or advice.
- The new tier must not be presented as trade eligibility or a recommendation; the table carries an explicit provisional banner.

## Acceptance

- A per-member `swing-analysis-research-tier@v1` object and document-level counts exist.
- The audit archetypes resolve as: BANKBARODA -> `RESEARCH_WATCH` (volume and weekly moderate, candle strong); UNIONBANK -> `RESEARCH_WATCH` (volume moderate, weekly weak, candle strong); BSE -> `RESEARCH_WATCH` (volume weak, weekly moderate, candle moderate); BHARTIARTL -> `NOT_QUALIFIED` via the 4.60 ATR risk ceiling; LT -> `NOT_QUALIFIED`; AXISBANK/TVSMOTOR/GMRAIRPORT -> `NOT_QUALIFIED` via the risk ceiling or two weak soft gates.
- The latest retained page (2026-11-23) yields `RESEARCH_WATCH` for EICHERMOT, ULTRACEMCO and EXIDEIND, and `NOT_QUALIFIED` for AXISBANK and GODREJCP, without changing the strict outcomes.
- The strict `swing-analysis-policy@v1` outcome and existing facts remain unchanged for the same input.
- The CLI reads a verified analysis file without provider access and emits the tier report.
- The daily report and ledger recompute the tier from facts and show it with flags.
- Tests cover strong/moderate/weak, hard failure, hard unavailable, risk ceiling, summary counts, forged precomputed labels, unverified analysis identity, impossible candle/volume values, and extreme risk.
- The strict policy is unchanged on a fresh normal `swing-analysis --scan-json` run over the retained 2026-11-23 page: 5 `NOT_QUALIFIED`, 0 `QUALIFIED`/`WATCH`/`INSUFFICIENT`.
- Ruff, Pyright, focused and full test/coverage gates, independent functional/domain and security/privacy reviews, hosted CI, and exact merge admission pass.

## Non-goals

- Replacing or relaxing the strict `QUALIFIED` policy.
- Changing scan candidate detection, BOS, safety, retest, demand, ATR, support/resistance, or provider acquisition.
- Any promotion of the new tier into live eligibility in this slice.
- Execution, targets, returns, rankings, position sizing, or advice.
- A full walk-forward calibration engine; the audit remains the initial hypothesis and the tier is shadow-only.

## Known limits

- The audit is one range/transition month, 27 unique candidates (11 mature), and uses scan snapshots rather than official closes.
- The 3.5 ATR and soft thresholds are hypotheses; they must be tested on a larger sample with explicit entry/stop/exit, costs and drawdown before any promotion.
- `RESEARCH_WATCH` increases recall and will include false positives; it must never be labelled `QUALIFIED` or investable.
