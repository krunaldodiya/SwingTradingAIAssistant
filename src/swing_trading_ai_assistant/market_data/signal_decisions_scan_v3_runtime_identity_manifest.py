"""Source-at-rest identities for the automated Nifty 100 scan policy."""

from typing import Final

SIGNAL_DECISIONS_SCAN_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/signal_decisions_scan_v3.py": "31fd62ee01e33176f9fa3a120505b7ab4d7a7b86dd949b040327303e4c1a7f79",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "496bda08233e465b4773153bfb04014707dd742791a08a27491b61acbbf5849c",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3.py": "6c01c1a31ce72b39e6e74413c7e6f0d9148c05445f891768dfb38ef81850ed43",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/current_stock_research_v2.py": "5fefdd72b70496d4526b50d447e7720cca703525b3c24c006051d8f13dea42e7",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
}
