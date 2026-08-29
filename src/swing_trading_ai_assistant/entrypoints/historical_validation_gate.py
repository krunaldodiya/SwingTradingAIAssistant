"""Import-safe console bootstrap for the historical validation gate."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Load the gate only inside the public sanitized exception boundary."""

    try:
        from ..historical_evaluation.capability_validation_cli import (  # noqa: PLC0415
            main as run,
        )

        return run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
