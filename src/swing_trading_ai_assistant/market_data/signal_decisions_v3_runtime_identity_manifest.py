"""Source-at-rest identities for the automated supported signal policy."""

from typing import Final

SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3.py": "90c3c861243889d3d1e1a99f7583357183142eea29894db8f62efc350a2ea545",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "496bda08233e465b4773153bfb04014707dd742791a08a27491b61acbbf5849c",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v4.py": "7830a368674eb639d2cb173e184e440db3a38066a0e551f46a634aea09358d5e",
    "src/swing_trading_ai_assistant/research_comparison/setup_first_inclusion_close.py": "fb876ef39988c2668377727a7d8fc9121a05ccce07f04f4955aeb83055d5b064",
    "src/swing_trading_ai_assistant/research_comparison/setup_observation_comparison.py": "a65f14afcff50946283f94c2350b794e13eb885b6f375956c037348f786e5a75",
    "src/swing_trading_ai_assistant/research_packet/bharatstock.py": "3c069177245684811588e3a8cb8a77b3835d8823073ede6b0de5f97a93a59abc",
    "src/swing_trading_ai_assistant/research_packet/bharatstock_v2.py": "973275d0f00c79efe16b292a9d4c2b147ce452e572b59d88af3580dfa0d7bbd3",
}
