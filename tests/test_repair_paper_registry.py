from __future__ import annotations

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "repair_paper_registry",
    Path(__file__).parents[1] / "scripts" / "repair_paper_registry.py",
)
assert spec is not None and spec.loader is not None
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "data"
    bars = (
        storage / "bharatstock-session-cache-v1" / "isin=INE000A01001" / "exchange=NSE"
    )
    bars.mkdir(parents=True)
    (bars / "session=2026-11-02.json").write_text(
        json.dumps(
            {
                "session": "2026-11-02",
                "high": "120",
                "low": "110",
                "close": "115",
            }
        )
    )
    registry = storage / "paper-observations-v1"
    registry.mkdir()
    for price in ("118", "121"):
        legacy = f"{price}".replace(".", "") * 8
        legacy = legacy[:32].ljust(64, "a")
        (registry / f"{legacy}.json").write_text(
            json.dumps(
                {
                    "schema": "paper-observation@v1",
                    "trade_id": legacy,
                    "symbol": "AAA",
                    "isin": "INE000A01001",
                    "exchange": "NSE",
                    "entry_session": "2026-11-02",
                    "entry_price_inr": price,
                    "stop_reference_inr": "105",
                    "risk_per_share_inr": "13",
                    "status": "ACTIVE",
                }
            )
        )
    return storage


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    before = sorted(path.name for path in (storage / "paper-observations-v1").iterdir())

    code = repair.main(
        ["--storage-root", str(storage), "--dry-run", "--output", "json"]
    )

    after = sorted(path.name for path in (storage / "paper-observations-v1").iterdir())
    assert code == 0
    assert after == before


def test_repair_collapses_to_one_record_per_setup(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    code = repair.main(["--storage-root", str(storage)])

    files = list((storage / "paper-observations-v1").glob("*.json"))
    assert code == 0
    assert len(files) == 1
    record = json.loads(files[0].read_text())
    assert record["entry_price_inr"] == "115"
    assert record["risk_per_share_inr"] == "10"


def test_invalid_root_is_rejected(tmp_path: Path) -> None:
    assert repair.main(["--storage-root", str(tmp_path / "missing")]) == 2
