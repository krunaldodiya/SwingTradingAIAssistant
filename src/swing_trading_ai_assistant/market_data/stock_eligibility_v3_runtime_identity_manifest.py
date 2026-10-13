"""Source-at-rest identities for the automated stock eligibility policy."""

from typing import Final

STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "1be887c1c7d47fefeb73a0a08c28c5f08873b271a280a17f8ce6968cc61d6bb8",
    "src/swing_trading_ai_assistant/market_data/bharatstock.py": "15b98327b6eff6a8e5b2c95cca1ab726872e11a7461f145487e81535b41728e3",
    "src/swing_trading_ai_assistant/market_data/corporate_actions.py": "65507d4b4dc08f33a871716c77b5b04fbfdc01fbc08ef1d224a620991c4973fb",
    "src/swing_trading_ai_assistant/market_data/credentials.py": "bc6b8847a2c57647071d636a43bcb82b3521bfe435944ce289822fbf583b675b",
    "src/swing_trading_ai_assistant/market_data/http.py": "ef5becb9960502f2808c3353099fc285de4d908d2eae7da65816266e2d02cd6e",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/upstox_full_quote_v3.py": "4c89f5f831394604644632c59d2a1f85d94e95034d8b3702228335a8365fc36b",
}
