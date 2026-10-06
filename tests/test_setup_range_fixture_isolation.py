"""Guarded range demonstration cannot disrupt later retained archive contracts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import test_setup_range_distribution as range_fixtures

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def guarded_range_reports():
    return range_fixtures.actual_reports.__wrapped__()


def _legacy(name: str) -> Any:
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = ROOT / "tests" / "sector_analysis" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_guarded_range_fixture_preserves_real_context_archive(
    guarded_range_reports, tmp_path
):
    assert guarded_range_reports["contains"][0] == 0
    _legacy(
        "test_current_industry_participation_v4"
    ).test_observed_v4_rows_are_aggregate_only_sorted_reconciled_and_identified(
        tmp_path
    )


def test_guarded_range_fixture_preserves_real_classification_archive(
    guarded_range_reports, tmp_path
):
    assert guarded_range_reports["contains"][0] == 0
    _legacy(
        "test_current_industry_participation"
    ).test_reduces_one_same_pass_observed_cohort_to_deterministic_industry_counts(
        tmp_path
    )
