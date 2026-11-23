import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.portfolio.accounts import add_account
from swing_trading_ai_assistant.portfolio.errors import PortfolioError
from swing_trading_ai_assistant.portfolio.snapshot import (
    import_snapshot,
    load_latest_snapshot,
)

_CSV = (
    "symbol,exchange,quantity,average_price,last_price,previous_close,isin\n"
    "HDFCBANK,NSE,100,790.58,829.85,846.00,INE040A01034\n"
)
_NOW = datetime(2026, 11, 23, 6, 35, tzinfo=UTC)


def _prepare(tmp_path: Path) -> Path:
    add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    source = tmp_path / "holdings.csv"
    source.write_text(_CSV, encoding="utf-8")
    import_snapshot(
        tmp_path,
        account_id="manual-main",
        file_path=source,
        as_of="2026-11-23T11:30:00+05:30",
        now=_NOW,
    )
    return sorted(
        (tmp_path / ".portfolio-accounts-v1" / "snapshots" / "manual-main").glob(
            "*.json"
        )
    )[0]


def _holding_mutation(key: str, value: object) -> Callable[[dict[str, object]], None]:
    def mutate(payload: dict[str, object]) -> None:
        holdings = payload["holdings"]
        assert isinstance(holdings, list)
        holding = holdings[0]
        assert isinstance(holding, dict)
        holding[key] = value

    return mutate


_MUTATIONS: list[Callable[[dict[str, object]], None]] = [
    lambda payload: payload.pop("source"),
    lambda payload: payload.__setitem__("source", "OTHER"),
    lambda payload: payload.__setitem__("account_id", 1),
    lambda payload: payload.__setitem__("as_of", "bad"),
    lambda payload: payload.__setitem__("imported_at", "bad"),
    lambda payload: payload.__setitem__("input_sha256", "bad"),
    lambda payload: payload.__setitem__("schema_version", 2),
    lambda payload: payload.__setitem__("schema_version", True),
    lambda payload: payload.__setitem__("holdings", []),
    lambda payload: payload.__setitem__("holdings", "bad"),
    lambda payload: payload.__setitem__("rejected", "bad"),
    lambda payload: payload.__setitem__("limitations", "bad"),
    lambda payload: payload.__setitem__("limitations", [1]),
    lambda payload: payload.__setitem__("rejected", [1]),
    lambda payload: payload.__setitem__("rejected", [{}]),
    lambda payload: payload.__setitem__(
        "rejected", [{"row": 0, "symbol": None, "reason": "X"}]
    ),
    lambda payload: payload.__setitem__(
        "rejected", [{"row": 1, "symbol": 1, "reason": "X"}]
    ),
    lambda payload: payload.__setitem__(
        "rejected", [{"row": 1, "symbol": None, "reason": ""}]
    ),
    lambda payload: payload.__setitem__("holdings", [{}]),
    _holding_mutation("symbol", "bad symbol"),
    _holding_mutation("exchange", "BSE"),
    _holding_mutation("isin", "bad"),
    _holding_mutation("quantity", "not-a-number"),
]


@pytest.mark.parametrize("mutation", _MUTATIONS)
def test_corrupt_snapshot_payload_rejected(
    tmp_path: Path, mutation: Callable[[dict[str, object]], None]
) -> None:
    path = _prepare(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutation(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(tmp_path, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_non_mapping_snapshot_rejected(tmp_path: Path) -> None:
    path = _prepare(tmp_path)
    path.write_text("[]", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(tmp_path, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_invalid_utf8_input_rejected(tmp_path: Path) -> None:
    add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    source = tmp_path / "holdings.csv"
    source.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PortfolioError) as error:
        import_snapshot(
            tmp_path,
            account_id="manual-main",
            file_path=source,
            as_of="2026-11-23T11:30:00+05:30",
            now=_NOW,
        )
    assert error.value.code == "INPUT_UNREADABLE"


def test_naive_now_rejected(tmp_path: Path) -> None:
    add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    source = tmp_path / "holdings.csv"
    source.write_text(_CSV, encoding="utf-8")
    with pytest.raises(PortfolioError) as error:
        import_snapshot(
            tmp_path,
            account_id="manual-main",
            file_path=source,
            as_of="2026-11-23T11:30:00+05:30",
            now=datetime(2026, 11, 23, 6, 35),
        )
    assert error.value.code == "INVALID_ARGUMENT"


def test_snapshot_directory_permissions_rejected(tmp_path: Path) -> None:
    path = _prepare(tmp_path)
    os.chmod(path.parent, 0o755)  # noqa: S103 - deliberately unsafe fixture
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(tmp_path, "manual-main")
    assert error.value.code == "SNAPSHOT_PERMISSIONS"


def test_missing_snapshot_file_rejected(tmp_path: Path) -> None:
    path = _prepare(tmp_path)
    path.unlink()
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(tmp_path, "manual-main")
    assert error.value.code == "NO_SNAPSHOT"
