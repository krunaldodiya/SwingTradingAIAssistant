from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def _module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "g09_series_report.py"
    spec = importlib.util.spec_from_file_location("g09_series_report", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_series_report_aggregates_pages(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    module = _module()
    monkeypatch.setattr(module, "_select", lambda *args, **kwargs: ["a", "b"])

    def page(root: Path, handle: str) -> dict[str, object]:
        return {
            "handle": handle,
            "state": "COMPLETE",
            "candidate_rows": 2,
            "candidate_hits": 1,
            "missed_opportunities": 0,
            "opportunities": 3,
        }

    monkeypatch.setattr(module, "_page", page)
    assert module.main(["--storage-root", str(tmp_path), "--output", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "g09-series-report@v1"
    assert report["series_state"] == "COMPLETE"
    assert report["summary"] == {
        "pages": 2,
        "complete": 2,
        "partial": 0,
        "unavailable": 0,
        "candidate_rows": 4,
        "candidate_hits": 2,
        "missed_opportunities": 0,
        "opportunities": 6,
    }
    assert report["report_identity_sha256"]


def test_series_page_uses_grader_keyword(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _module()
    seen: list[str] = []

    def grade(root: Path, *, decision_evidence: str | None = None) -> dict[str, object]:
        assert root == tmp_path
        assert decision_evidence == "handle"
        seen.append("called")
        return {
            "report_state": "COMPLETE",
            "summary": {"candidate_rows": 1, "candidate_hits": 1},
            "window": {"decision_session": "2026-10-26", "state": "COMPLETE"},
            "page": {"scan_timestamp": "2026-10-26T15:00:00.000000Z"},
            "report_identity_sha256": "x",
        }

    monkeypatch.setattr(module, "grade_scan_decision_evidence_v1", grade)
    page = module._page(tmp_path, "handle")
    assert seen == ["called"]
    assert page["state"] == "COMPLETE"
    assert page["candidate_rows"] == 1
