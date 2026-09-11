from __future__ import annotations

import sys
from importlib import util
from pathlib import Path
from types import SimpleNamespace

import pytest

from swing_trading_ai_assistant.sector_analysis import (
    current_industry_participation_v4 as industry,
)


def _load(relative, name):
    path = Path(__file__).parents[1] / relative
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _with_industry(tmp_path, inspect):
    context_test = _load(
        "market_regime/test_bharatstock_regime_v4.py", "industry_v4_context_fixture"
    )
    classification_test = _load(
        "sector_analysis/test_current_industry_participation_v4.py",
        "industry_v4_classification_fixture",
    )

    def inspect_context(scenario, request, context):
        classification = classification_test._retained_classification(
            tmp_path / "classification", context, SimpleNamespace(request=request)
        )
        result = industry.reduce_current_industry_participation_v4(
            context, classification
        )
        assert result.evidence_state == "OBSERVED"
        assert industry.current_industry_participation_is_exact_valid_v4(
            result, context
        )
        inspect(scenario, request, context, classification, result)

    context_test.test_public_v4_retains_complete_context_and_replays_exact_bytes(
        tmp_path, None, inspect_context
    )


def test_retained_v4_industry_preserves_breadth_and_missing_classification(tmp_path):
    def inspect(_scenario, _request, context, classification, result):
        assert sum(row.unchanged for row in result.industries) == 1
        assert sum(row.advances + row.declines for row in result.industries) == 0
        fixtures = _load(
            "sector_analysis/test_current_industry_participation_v4.py",
            "industry_v4_failure_fixture",
        )
        failed = industry.reduce_current_industry_participation_v4(
            context, fixtures._classification_failure("CLASSIFICATION_ARTIFACT_MISSING")
        )
        assert failed.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert failed.industries is None
        with pytest.raises(TypeError):
            industry.reduce_current_industry_participation_v4(object(), classification)

    _with_industry(tmp_path, inspect)
