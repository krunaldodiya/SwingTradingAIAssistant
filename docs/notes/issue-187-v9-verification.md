# Issue #187 V9 verification evidence

## Scope

Corrective pass from V8 commit `57624f193c76681852041f42c73bb93b54c42391`.

## Focused regression evidence

- Mapping V2 now rejects retained same-pass context evidence whose canonical
  member interval is no longer current; this is exercised by
  `test_failed_context_mapping_with_expired_member_is_not_admitted` and both
  context-state variants of
  `test_v5_rejects_same_pass_context_with_expired_canonical_mapping`.
- V5 writer admission is exercised at its exact 50,000-node boundary and at
  limit-plus-one by
  `test_v5_writer_preflight_refuses_limit_plus_one_before_serialization`.
  The overflow assertion verifies the refusal counter and confirms that no
  canonical call was recorded before admission.

## Commands observed green

```text
uv run --no-sync --extra dev pytest \
  tests/market_data/test_current_stock_research.py \
  tests/market_data/test_current_research_binding_v2.py \
  tests/market_data/test_current_event_notice_v2.py \
  tests/research_packet/test_current_research_packet_v5.py -q --no-cov
# 114 passed

uv run --no-sync --extra dev ruff check src/swing_trading_ai_assistant \
  tests/research_packet/test_current_research_packet_v5.py
# All checks passed

uv run --no-sync --extra dev pyright
# 0 errors, 0 warnings, 0 informations
```

A direct SHA-256 check also verified every entry in the V4, mapping V2, Event
V2, BharatStock V2, V5, stock-research V2, and market-data runtime manifests;
the six successor runtime-identity functions returned 64-character identities.

## Full-suite boundary

`uv run --no-sync --extra dev pytest -q --no-cov` completed with **4,681
passed** and **4 failed**.  The failures are all pre-existing
`@pytest.mark.private_source` historical-Upstox tests that require the owner
private catalog at `~/SwingTradingAIAssistantData`; they fail with insufficient
retained evidence/catalog identity before Issue #187 code is exercised.  The
Issue #187 focused portfolio above is green.

## Package evidence

`uv build --out-dir /private/tmp/issue187-dist` completed successfully,
producing the V9 sdist and wheel outside the repository:

- wheel SHA-256: `1d477f7fe1b0637d5faa64982ca03e9b70ec3f4d2c1c887a2967242f48f7b1cb`
- sdist SHA-256: `6b70a833a8183f95a7eb2177ffa0d15a4df4f2fc55137840d6da9e31d7274446`
