"""Source-at-rest identities for the automated stock eligibility policy."""

from typing import Final

STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V3: Final[dict[str, str]] = {
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py": "496bda08233e465b4773153bfb04014707dd742791a08a27491b61acbbf5849c",
    "src/swing_trading_ai_assistant/market_data/bharatstock.py": "2924ed4e35c8195029bb58ca711bb049d8d0a0d939f7a69146c19265c491ea52",
    "src/swing_trading_ai_assistant/market_data/bharatstock_capture.py": "9b529bb2f413ac58d5e14e545380409a18c10b797dd913cb24536a90f3f92d2a",
    "src/swing_trading_ai_assistant/market_data/corporate_actions.py": "65507d4b4dc08f33a871716c77b5b04fbfdc01fbc08ef1d224a620991c4973fb",
    "src/swing_trading_ai_assistant/market_data/credentials.py": "bc6b8847a2c57647071d636a43bcb82b3521bfe435944ce289822fbf583b675b",
    "src/swing_trading_ai_assistant/market_data/http.py": "ef5becb9960502f2808c3353099fc285de4d908d2eae7da65816266e2d02cd6e",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py": "834fb3261a269b35e582d91b7c497be276bd102078bb9d71816fe2f77a4c721a",
    "src/swing_trading_ai_assistant/market_data/schedule_evidence.py": "2894a34356c7d12c71cf2a9cb133d0a5d7aaa83a83d7ac43549a13e7b9081801",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py": "01e59ddaa39d3d0020c5e7ee51dfa5a88a0ffee6d5f950f88f2a3ceabe0d585e",
    "src/swing_trading_ai_assistant/market_data/storage_root_lease.py": "f93eac4f668dbdb0e236a3a54452a8d022c5700e91452536acafb1300b22f6ff",
    "src/swing_trading_ai_assistant/market_data/upstox_full_quote_v3.py": "bb0c4311777d2d23ab184f33f6cebf187b1dbb50f309b8ea1b501c3d12656578",
}
