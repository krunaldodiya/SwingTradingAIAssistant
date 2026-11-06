#!/usr/bin/env python3
"""Repair the paper-observation registry so each setup has exactly one record.

Earlier registry entries took their entry price from the price on the day the
candidate was noticed, and derived the trade identity from that price. A candidate
is republished for up to five sessions, so the same setup was registered again on
every pass and the aggregates counted overlapping positions.

This command groups by ``(symbol, entry_session)``, re-prices each setup from the
retained event-session close, keeps one canonical record and removes the rest. A
setup whose session close is missing, or whose stop is at or above the entry, is
reported instead of rewritten: inventing an entry price would be worse than an
admitted gap.

Read-only with ``--dry-run``. Exit codes: 0 reported, 2 invalid input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swing_trading_ai_assistant.market_data.paper_tracking import repair_registry

SCHEMA = "paper-registry-repair@v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", choices=("table", "json"), default="table")
    args = parser.parse_args(argv)

    root = Path(args.storage_root)
    if not root.is_dir():
        print("paper_repair_invalid: storage root unavailable", file=sys.stderr)
        return 2

    result = repair_registry(root, dry_run=args.dry_run)
    if args.output == "json":
        print(json.dumps(result, indent=1))
        return 0

    prefix = "would repair" if args.dry_run else "repaired"
    print(
        f"{result['records_read']} record(s), {result['setups']} setup(s): "
        f"{prefix} {result['repaired']}, "
        f"duplicates removed {result['duplicates_removed']}, "
        f"unrepairable {result['unrepairable']}, "
        f"stop conflicts {result['stop_conflicts']}"
    )
    if args.dry_run:
        print("dry run: nothing was written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
