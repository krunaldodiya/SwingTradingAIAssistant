"""Installed market-data entrypoint with isolated additive command dispatch."""

from __future__ import annotations

import sys

from .cli import main as existing_main
from .current_stock_observation_comparison_cli import main as comparison_main


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0] == "research-compare":
        return comparison_main(raw)
    return existing_main(raw)


__all__ = ["main"]
