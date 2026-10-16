# Plan 73: paper observation tracking registry and forward candidate monitoring

Status: accepted bounded specification under [Issue #316](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/316), Milestone 51. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research policy, paper execution tracking, and public decision contracts. Base: `24ea96a`.

## Outcome and consumer

A human trader and an external AI agent harness can log confirmed `RESEARCH_CANDIDATE` swing setups from `signal-decisions scan` into an immutable paper-tracking registry (`paper-observations-v1`), and monitor their performance forward in time across the 5–10 trading session swing window:

```bash
# Log new candidates from a scan and update tracking status:
signal-decisions track --storage-root ROOT --log-scan scan_result.json --output table

# Display current paper trade portfolio tracking status:
signal-decisions track --storage-root ROOT --output table
```

This delivers Outcome G11 on the project roadmap: proving forward swing performance with zero real-money risk before any capital or broker integration is introduced.

## Core rules and state transitions

1. **Trade Registration:**
   * When a stock is identified as `RESEARCH_CANDIDATE`, it is recorded with:
     - `entry_session`: The candidate confirmation session.
     - `entry_price_inr`: Current quote price at the scan time.
     - `stop_reference_inr`: The structural swing-low protective stop.
     - $R$ (Risk per share): $\text{entry\_price} - \text{stop\_reference}$.
     - Milestone targets: $1R = \text{entry} + R$, $2R = \text{entry} + 2R$, $3R = \text{entry} + 3R$.
     - Initial status: `ACTIVE`.

2. **Daily Forward Monitoring & Invalidation:**
   For every `ACTIVE` paper trade, the tracker checks subsequent daily sessions:
   * **Invalidation (`INVALIDATED`):** If any daily candle closes strictly below `stop_reference_inr`, the position is stopped out at that close. `exit_session = bar.session`, `exit_price_inr = bar.close`, `return_multiple_r = (close - entry) / R`.
   * **Target Reached (`TARGET_REACHED`):** If the high of a subsequent daily bar touches or exceeds the $2R$ milestone ($\text{high} \ge 2R$), the $2R$ target is logged as reached.
   * **Window Expiry (`WINDOW_EXPIRED`):** If 10 completed trading sessions elapse without hitting the stop or the target, the position is finalized at the 10th session close.

3. **Performance Metrics:**
   The tracker computes aggregate performance across all resolved paper trades:
   * Win rate: $\frac{\text{trades with } R > 0}{\text{total resolved trades}} \times 100$.
   * Average $R$-multiple achieved.
   * Total $R$ profit / loss.

## Frozen schemas

### 1. `paper-trade-record@v1`
- `schema`: `"paper-trade-record@v1"`
- `trade_id`: 64-hex SHA-256
- `symbol`: str
- `isin`: str
- `exchange`: `"NSE"`
- `entry_session`: `"YYYY-MM-DD"`
- `entry_price_inr`: Decimal text
- `stop_reference_inr`: Decimal text
- `risk_per_share_inr`: Decimal text ($R$)
- `target_1r_inr`: Decimal text
- `target_2r_inr`: Decimal text
- `target_3r_inr`: Decimal text
- `status`: `"ACTIVE"` | `"INVALIDATED"` | `"TARGET_REACHED"` | `"WINDOW_EXPIRED"`
- `exit_session`: str or null
- `exit_price_inr`: Decimal text or null
- `return_multiple_r`: Decimal text or null
- `max_r_reached`: Decimal text
- `sessions_held`: int

### 2. `paper-tracking-report@v1`
- `schema`: `"paper-tracking-report@v1"`
- `report_timestamp`: ISO 8601 UTC
- `storage_root_sha256`: str
- `total_tracked_trades`: int
- `active_trades_count`: int
- `invalidated_count`: int
- `target_reached_count`: int
- `expired_count`: int
- `win_rate_percent`: str or null
- `average_r_return`: str or null
- `trades`: list of `paper-trade-record@v1`

## Non-goals

No real-money broker order execution, position sizing, margin calculations, or capital allocation.
