"""Source-at-rest identities for the automated supported signal policy."""

from typing import Final

SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3.py": "ee09af2973e166fbe5b352daf234a68bb963ddd55caad90d411f3881850e4622",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "496bda08233e465b4773153bfb04014707dd742791a08a27491b61acbbf5849c",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v4.py": "715ad59bf0b7180947df7344aa013931e6f5366fddbea2a3bcda2e4fb8c7388a",
    "src/swing_trading_ai_assistant/research_comparison/setup_first_inclusion_close.py": "aeedcb69c34e9635ae764f55b1a8a49afaa45856638a5776597244f2936597c9",
    "src/swing_trading_ai_assistant/research_comparison/setup_observation_comparison.py": "69f95c6479e4cfabdee66e788292f07c3ad33ebfa015727ceafe99de009b7070",
    "src/swing_trading_ai_assistant/research_packet/bharatstock.py": "3c069177245684811588e3a8cb8a77b3835d8823073ede6b0de5f97a93a59abc",
    "src/swing_trading_ai_assistant/research_packet/bharatstock_v2.py": "973275d0f00c79efe16b292a9d4c2b147ce452e572b59d88af3580dfa0d7bbd3",
}
