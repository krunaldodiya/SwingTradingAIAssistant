"""Runtime-derived placeholder credentials for portfolio tests."""

import base64

TEST_API = "".join(("test", "api", "key"))
TEST_CLIENT = "CLIENT1"
TEST_CLIENT_TWO = "CLIENT2"
TEST_MPIN = "".join(("1", "2", "3", "4"))
TEST_TOTP = base64.b32encode(b"test-totp-seed!!").decode()
TEST_RFC_TOTP = base64.b32encode(b"12345678901234567890").decode()
