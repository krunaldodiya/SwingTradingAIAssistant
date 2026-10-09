"""Source-at-rest identities for the automated stock eligibility policy."""

from typing import Final

STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "a910988a4991b9c7c2d608f8126ab9311a20b8e735b9ee3aa4d2aaaf81c4d0cd",
    "src/swing_trading_ai_assistant/market_data/bharatstock.py": "4f43a61d44f9a907cc9274ab3ca3403854049b1c39f379b5730ca3d044bc78a1",
    "src/swing_trading_ai_assistant/market_data/corporate_actions.py": "65507d4b4dc08f33a871716c77b5b04fbfdc01fbc08ef1d224a620991c4973fb",
    "src/swing_trading_ai_assistant/market_data/credentials.py": "bc6b8847a2c57647071d636a43bcb82b3521bfe435944ce289822fbf583b675b",
    "src/swing_trading_ai_assistant/market_data/http.py": "ef5becb9960502f2808c3353099fc285de4d908d2eae7da65816266e2d02cd6e",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/upstox_full_quote_v3.py": "8badfa5ef04f09d31cca615e7cc56bd15e2651d1471e36087d18df3684799512",
}
