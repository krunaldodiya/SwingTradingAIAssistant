"""Source-at-rest identities for the signal decision policy."""

from typing import Final

SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V2: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/signal_decisions.py": "a0bd7db27cb44eada87dac61678661380785711d1b1c4ef164293ad77653b139",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility.py": "ea0f9769a40d191f5357372a32349e47607155da998f2388c12e4a3a62bd03b8",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_runtime_identity_manifest.py": "efa7975659430daf0ef9890c4db5f9e76aedd4380dcfbede62b006ef3d85018d",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/stock_observations_runtime_identity_manifest.py": "5d842365031ea3a7004d9ac2dfd8d220534ef259e840b2f60cc3b2296d11f198",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_cli.py": "5fe05c2b9021fb67efdd42e0b84c38dc5d18f1cd33879b63f4fb3b3a9aed50e3",
    "src/swing_trading_ai_assistant/entrypoints/signal_decisions.py": "cf22d6e4b4508f10ef902949835cdb06bc1d4f34e603f21646a79b6f95c13bfa",
}
