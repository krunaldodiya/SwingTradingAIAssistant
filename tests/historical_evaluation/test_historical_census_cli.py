from __future__ import annotations

import json
from pathlib import Path

from swing_trading_ai_assistant.historical_evaluation.cli import main


def test_cli_emits_canonical_provider_free_report(tmp_path: Path, capsys) -> None:
    seal = {
        "provider_attempt_count": 0,
        "stock_count": 50,
        "partition_count": 100,
        "dataset_identity_sha256": "a" * 64,
        "selections": [
            {"isin": f"INE{i:08d}0", "month": month}
            for i in range(50)
            for month in ("2026-07", "2026-08")
        ],
    }
    path = tmp_path / "seal.json"
    path.write_text(json.dumps(seal))
    args = [
        "--seal",
        str(path),
        "--code-sha",
        "b" * 40,
        "--configuration-sha256",
        "c" * 64,
    ]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert json.loads(first)["provider_attempt_count"] == 0
    assert main(args) == 0
    assert capsys.readouterr().out == first


def test_cli_sanitizes_bad_seal(tmp_path: Path, capsys) -> None:
    path = tmp_path / "seal.json"
    path.write_text("{}")
    assert (
        main(
            [
                "--seal",
                str(path),
                "--code-sha",
                "b" * 40,
                "--configuration-sha256",
                "c" * 64,
            ]
        )
        == 3
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "historical census unavailable\n"
