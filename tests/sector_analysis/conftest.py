"""Shared admitted Market Regime facts for Sector Participation tests."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

from swing_trading_ai_assistant.market_regime import (
    VerifiedMarketRegimeFactsV1,
    admit_verified_market_regime_facts_v1,
)


def _fact_graph_module() -> ModuleType:
    loaded = sys.modules.get("test_fact_graph")
    if loaded is not None:
        return loaded

    path = Path(__file__).parents[1] / "market_regime" / "test_fact_graph.py"
    spec = importlib.util.spec_from_file_location("test_fact_graph", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("fact graph fixture is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def verified_market_regime_facts_v1() -> VerifiedMarketRegimeFactsV1:
    valid_graph = cast(
        Callable[[], dict[str, Any]],
        _fact_graph_module()._valid_graph,
    )
    return admit_verified_market_regime_facts_v1(**valid_graph())
