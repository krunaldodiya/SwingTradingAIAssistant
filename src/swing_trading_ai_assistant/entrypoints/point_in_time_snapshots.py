"""Import-safe console bootstrap for bounded point-in-time evidence snapshots."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Load the snapshot CLI only inside the public sanitized exception boundary."""

    try:
        from ..market_data.point_in_time_snapshot_v1_cli import (  # noqa: PLC0415
            main as run,
        )

        return run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
