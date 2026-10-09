"""Source-at-rest identities for the automated stock eligibility policy."""

from typing import Final

STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "6891c0b05e0d95faa748f20198d41b245e4f76b77c8bd333bdb400f17001810f",
    "src/swing_trading_ai_assistant/market_data/bharatstock.py": "4f43a61d44f9a907cc9274ab3ca3403854049b1c39f379b5730ca3d044bc78a1",
    "src/swing_trading_ai_assistant/market_data/corporate_actions.py": "1d74c5cc7e94470452377491d5fa6ead801833bb4f17b4bae3305e73058cd9cc",
    "src/swing_trading_ai_assistant/market_data/credentials.py": "bc6b8847a2c57647071d636a43bcb82b3521bfe435944ce289822fbf583b675b",
    "src/swing_trading_ai_assistant/market_data/http.py": "ef5becb9960502f2808c3353099fc285de4d908d2eae7da65816266e2d02cd6e",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/upstox_full_quote_v3.py": "c0f135dd3606fd4a96b7ef3fc50edb2ed246633ad1f649297549d5f7e4dc16f9",
}
