from __future__ import annotations

import json
from pathlib import Path

from swing_trading_ai_assistant.historical_evaluation.cli import main

FIXTURES = Path(__file__).parents[1] / "fixtures" / "historical_evaluation"
REAL_SEAL = FIXTURES / "retained-seal.json"


def args(path: Path = REAL_SEAL) -> list[str]:
    return [
        "--seal",
        str(path),
        "--evidence-seal-sha256",
        "3c0450aa4885dcfbf7f1e94673a2b4fec402b184dd7d224d849b4a44e537d809",
        "--universe",
        str(FIXTURES / "universe.json"),
        "--schedule",
        str(FIXTURES / "schedule-july.json"),
        "--schedule",
        str(FIXTURES / "schedule-august.json"),
        "--data-manifest",
        str(FIXTURES / "coverage-manifest.json"),
        "--observation-cutoff",
        "2026-08-12T15:30:00Z",
        "--code-sha",
        "b" * 40,
        "--configuration-sha256",
        "c" * 64,
    ]


def test_cli_emits_repeatable_canonical_provider_free_report(capsys) -> None:
    assert main(args()) == 0
    first = capsys.readouterr().out
    assert json.loads(first)["provider_attempt_count"] == 0
    assert main(args()) == 0
    assert capsys.readouterr().out == first


def test_cli_sanitizes_bad_seal(tmp_path: Path, capsys) -> None:
    path = tmp_path / "seal.json"
    path.write_text("{}")
    assert main(args(path)) == 3
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "historical census unavailable\n"
