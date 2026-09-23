# Swing research when the latest daily candle is delayed

**Decision:** accepted by the owner on 2026-09-23. **Implementation:** Sprint 23
[issue #215](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/215)
adds this behavior to `research-run-current --contract-version v2`. The default
`v1` agent output and existing stock-research V1/V2 questions retain their
strict latest-completed-session behavior.

**Owner and risk:** the repository owner directs this research behavior. Its
implementation is R3 because session selection changes public financial
research evidence. The affected consumers are the agent-run dossier and any
later strategy that reads it; historical snapshots, credentials, provider
choice and the 21-session calculation are unchanged. The one-session bound is
reviewed again if a strategy's accepted freshness rule requires S itself.

The product researches multi-day swing trades, commonly held for about 5–10
trading days. A late provider publication of one daily candle should not erase
the independently usable 21-session price history. It also must not turn
yesterday's evidence into a claim about today's completed session.

Keeping the strict S-only rule loses otherwise usable swing context during a
provider delay. Searching back without a limit risks treating old evidence as
current. The selected compromise permits one prior official session, makes the
lag visible, and leaves strategy-specific freshness to the later signal gate.

## Session choice

Resolve the latest officially completed NSE trading session from the
authoritative schedule at the decision cutoff; call it **S**. Market hours,
weekends and holidays do not by themselves create a fallback: before today's
official close, S is already the prior completed trading session.

1. Prefer the exact 21 consecutive official sessions ending at S (S and the
   previous 20). Acquire or reuse admitted BharatStock evidence under the
   existing source, identity, cutoff, schedule and storage rules.
2. If the provider has not supplied S's **completed** daily bar, try exactly
   one earlier anchor, the immediately preceding official trading session P.
   Confirm S is still absent after the wider S-anchored captures, within the
   original decision deadline; an observed S fact or an invalid/conflicting
   wider outcome blocks fallback. The versioned mode may acquire up to 40
   calendar days of official schedule on its initial, confirmation, and P-anchored requests
   solely to establish S plus 21 prior sessions after holidays; the default
   public V2 question retains its 32-day request.
   The agent run uses a distinct capture request identity to mark a missing
   terminal S only when the provider returns exactly the preceding requested
   rows for the correct stock within the original cutoff. Ambiguous legacy
   `HISTORY_INCOMPLETE` never qualifies. The public V2 research question keeps
   its existing request shape and failure-reason behavior; changed runtime
   source identity naturally gives new captures new request hashes.
   If P's complete window fails after some independent P facts were admitted,
   keep the selected dossier unset and expose those P feature outcomes only in
   a separate `previous_window_attempt` record with its anchor and provenance.
   Require a complete, admitted 21-session window ending at P (P and its
   previous 20). Shift the one-session candle, two-session previous-close and
   21-session structure windows **together** for that stock. Do not mix a
   candle from S with structure ending at P and call the result current.
3. Report the chosen end session, S, current evidence-known/selection times and
   a one-trading-session lag explicitly. Label every fact as ending at P. This
   is a recent completed-session study, not a completed-session fact for S.
   When S's admitted bar later appears, a new run should prefer S again.
4. If P's full window is unavailable, preserve independent feature-level
   outcomes and report the missing evidence. Do not search arbitrarily older
   windows or silently substitute the separate Upstox download store, another
   provider, partial intraday data, or a different price basis.

This fallback is only for a verified missing or not-yet-published S bar after
the schedule proves S officially completed. It does not bypass malformed or
conflicting bars, corporate-action or mapping failures, shared authentication
or rate-limit failures, unsafe storage, or an expired acquisition deadline.
Those retain their existing typed outcomes. The earlier 21-session window must
still pass the same provenance, comparability and calculation admission as the
normal window. Its data may be acquired now; do not represent it as known at a
past cutoff.

For a multi-stock run, each stock's chosen end session remains visible.
`jointly_comparable` cannot be true across different end sessions. A later
strategy or trade-signal contract decides whether one-session-lagged evidence
is sufficiently fresh for its claim; this decision does not authorize a
BUY/HOLD/EXIT signal or a new performance assertion.

The versioned agent result exposes `latest_official_completed_session`,
`selected_evidence_end_session`, `lag_official_sessions`, and
`fallback_outcome` for each stock. Its selected facts retain their source and
capture identities. Switching back to the default `v1` agent contract restores
S-only selection without deleting valid captured evidence.

## Acceptance examples for implementation

- After S closes and all 21 bars are admitted: use S plus the previous 20;
  report no provider lag.
- After S closes but its provider bar is absent, while P plus the previous 20
  are fully admitted: use P and explicitly report one trading-session lag.
- Before S closes, on a weekend or on a market holiday: use the latest
  *officially completed* session normally; do not call it a provider fallback.
- Missing P, only 20 earlier bars, a two-session gap, conflicting S, or an
  authentication/deadline failure: do not publish a 21-session fallback fact.
- One stock on S and another on P: preserve both stock facts with their own
  dates; do not claim the batch is jointly same-session comparable.

This corrects the 2026-09-23 ten-stock live observation: the first run saw
`EMPTY_HISTORY` for S and `HISTORY_INCOMPLETE` for the S-anchored wider
windows; a retry minutes later admitted the complete S-anchored 21 sessions.
The observed provider delay motivates a bounded, truthful fallback, not a
change to Market Structure's 21-session mathematics.
