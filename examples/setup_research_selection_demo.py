"""Exercise whole-list installed SDK/CLI using fixed synthetic evidence only."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from datetime import timedelta
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
from current_setup_research_demo import (  # noqa: E402 - existing synthetic collaborators
    NOW,
    IntegratedPrices,
    SyntheticClock,
    SyntheticOfficialSources,
    deny_protected_effects,
)

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.market_data.bharatstock_capture import CaptureRequestV2
from swing_trading_ai_assistant.market_data.cli import main as research_cli
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.efficient_current_nifty100_adjusted_capture import (
    NIFTY_50_URL,
    NIFTY_100_URL,
    NIFTY_NEXT_50_URL,
    SourceResponseV2,
    _retain_selection_v2,
    admit_current_nifty100_selection_v2,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)
from swing_trading_ai_assistant.market_data.instruments import (
    UPSTOX_NSE_INSTRUMENTS_URL,
)
from swing_trading_ai_assistant.market_data.setup_research_selection import (
    run_setup_research_selection_current,
)

QUALIFICATION_REFERENCES: dict[str, object] = {}


def _symbols(count: int) -> tuple[str, ...]:
    return tuple(f"S{i:03d}" for i in range(count))


class SelectionSources(SyntheticOfficialSources):
    def __init__(self, scenario: str):
        super().__init__("complete")
        self.selection_scenario = scenario

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if url != UPSTOX_NSE_INSTRUMENTS_URL:
            return super().get(url, headers)
        rows = [
            {
                "segment": "NSE_EQ",
                "name": f"Company {i}",
                "exchange": "NSE",
                "isin": f"INE{i:09d}",
                "instrument_type": "EQ",
                "instrument_key": f"NSE_EQ|INE{i:09d}",
                "trading_symbol": s,
            }
            for i, s in enumerate(_symbols(100))
        ]
        if self.selection_scenario == "unknown-later":
            rows.pop(10)
        if self.selection_scenario == "canonical-conflict":
            rows[10]["isin"] = rows[0]["isin"]
            rows[10]["instrument_key"] = rows[0]["instrument_key"]
        return HttpResponse(
            200,
            gzip.compress(json.dumps(rows).encode(), mtime=0),
            HttpResponseHeaders.from_items((("Content-Type", "application/json"),)),
            request_url=url,
            response_url=url,
        )


class Witnesses:
    def get(self, url: str) -> SourceResponseV2:
        start, count = {
            NIFTY_50_URL: (0, 50),
            NIFTY_NEXT_50_URL: (50, 50),
            NIFTY_100_URL: (0, 100),
        }[url]
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("Company Name", "Industry", "Symbol", "Series", "ISIN Code"))
        writer.writerows(
            (f"Company {i}", "Industry", f"S{i:03d}", "EQ", f"INE{i:09d}")
            for i in range(start, start + count)
        )
        return SourceResponseV2(
            url, url, 200, stream.getvalue().encode(), NOW - timedelta(seconds=1)
        )


def _default(root: Path):
    selection = admit_current_nifty100_selection_v2(Witnesses())
    if selection is None:
        raise RuntimeError("synthetic witnesses not admitted")
    request = CaptureRequestV2(
        members=selection.members,
        sessions=(NOW.date() - timedelta(days=1),),
        decision_cutoff=NOW,
        schedule_evidence_sha256="1" * 64,
        schedule_source="nse-upstox-composed-calendar",
        schedule_source_release=f"composed-calendar@v1={'3' * 64}",
        schedule_identity_sha256="2" * 64,
        selection_identity_sha256=selection.selection_identity_sha256,
    )
    if not _retain_selection_v2(selection, request, root):
        raise RuntimeError("synthetic retention failed")
    path = root / "selection-request.json"
    path.write_bytes(
        (
            json.dumps(request.canonical_value(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
    )
    path.chmod(0o600)
    return request, path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "explicit11",
            "default100",
            "unknown-later",
            "negative",
            "geometry-missing",
            "interrupted",
            "canonical-conflict",
            "invalid101",
            "selection-unavailable",
        ),
        default="explicit11",
    )
    scenario = parser.parse_args().scenario
    sys.addaudithook(deny_protected_effects)
    sys.stderr.write(
        "SYNTHETIC WHOLE-LIST RESEARCH: fixed clock; not current market data.\n"
    )
    sources = SelectionSources(scenario)
    producer = partial(
        research_current_stock_v2,
        clock=SyntheticClock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(
            BharatStockClient,
            IntegratedPrices(
                scenario if scenario in {"negative", "geometry-missing"} else "positive"
            ),
        ),
    )
    results: dict[str, CurrentStockResearchResultV2] = {}
    calls = []

    def service(
        symbol: str, root: Path, *, question: str, refresh: bool
    ) -> CurrentStockResearchResultV2:
        calls.append((symbol, question, refresh))
        if scenario == "interrupted" and symbol == "S010":
            raise KeyboardInterrupt
        result = producer(symbol, root, question=question, refresh=refresh)
        results[symbol] = result
        return result

    with TemporaryDirectory(prefix="whole-list-research-demo-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        default = scenario in {"default100", "selection-unavailable"}
        request = None
        path = None
        if default:
            request, path = _default(root)
            if scenario == "selection-unavailable":
                (
                    root
                    / "nifty100-selection-v3"
                    / "requests"
                    / f"{request.request_identity_sha256}.json"
                ).unlink()
        count = (
            101
            if scenario == "invalid101"
            else 1
            if scenario in {"negative", "geometry-missing"}
            else 11
        )
        symbols = None if default else _symbols(count)
        args = [
            "setup-research-selection",
            "--storage-root",
            str(root),
            "--output",
            "json",
        ]
        if symbols is None:
            args += [
                "--selection-request-file",
                str(path),
                "--selection-root",
                str(root),
            ]
        else:
            args += [a for symbol in symbols for a in ("--symbol", symbol)]
        code = research_cli(
            args, current_stock_research_v2=service, trusted_clock=SyntheticClock()
        )
        QUALIFICATION_REFERENCES.clear()
        QUALIFICATION_REFERENCES["producer_calls"] = calls
        QUALIFICATION_REFERENCES["requested_symbols"] = list(
            _symbols(100) if default else symbols
        )
        if code in {0, 1} and scenario != "selection-unavailable":
            report = run_setup_research_selection_current(
                symbols,
                root,
                research=lambda s, *a, **kw: results[s],
                selection_request=request,
                selection_root=root if default else None,
                clock=SyntheticClock().now,
            )
            raw = (
                json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
            QUALIFICATION_REFERENCES["same_observation_sdk_identity"] = report[
                "result_identity_sha256"
            ]
            QUALIFICATION_REFERENCES["whole_output_sha256"] = hashlib.sha256(
                raw
            ).hexdigest()
        return code


if __name__ == "__main__":
    raise SystemExit(main())
