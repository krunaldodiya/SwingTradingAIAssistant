"""Import-safe console bootstrap for private Nifty 100 BharatStock V2 capture."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Load the V2 CLI without provider-specific runtime or native loaders."""

    try:
        from ..market_data.efficient_current_nifty100_adjusted_capture_cli import (  # noqa: PLC0415 - sanitize runtime import failures
            main as run,
        )

        return run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
