"""Import-safe console bootstrap for bounded current Nifty 100 capture."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Load the owner-private capture CLI inside its sanitized boundary."""

    try:
        from ..market_data.efficient_current_nifty100_adjusted_capture_cli import (  # noqa: PLC0415
            main as run,
        )

        return run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
