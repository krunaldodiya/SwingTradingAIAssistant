"""CLI adapter for two admitted current-stock V2 observations."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NoReturn, Protocol

from .bharatstock import (
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from .current_stock_observation_comparison import (
    compare_current_stock_observations_v1,
    invalid_current_stock_observation_comparison_v1,
)
from .current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    QuestionV2,
    research_current_stock_v2,
)
from .http import HttpResponse, HttpTransportError, ProviderErrorCategory


class CurrentStockObservationPortV1(Protocol):
    def __call__(
        self,
        symbol: str,
        storage_root: Path,
        *,
        question: QuestionV2,
        selection_time: datetime,
    ) -> CurrentStockResearchResultV2: ...


class _FixedClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


class _RetainedOnlyTransport:
    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        del url, headers
        raise HttpTransportError(ProviderErrorCategory.AUTHORIZATION)


class _RetainedOnlyPrices:
    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        del instrument, start, end
        if callable(effect_guard):
            effect_guard()
        raise BharatStockError("AUTHORIZATION", member_local=True)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _instant(value: str) -> datetime:
    if len(value) != 27:
        raise argparse.ArgumentTypeError(
            "expected UTC instant YYYY-MM-DDTHH:MM:SS.ffffffZ"
        )
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected UTC instant YYYY-MM-DDTHH:MM:SS.ffffffZ"
        ) from error


def _valid_symbol(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 32
        and value[0].isascii()
        and value[0].isalnum()
        and all(
            character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"
            for character in value
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="market-data research-compare")
    parser.add_argument("command", choices=("research-compare",))
    parser.add_argument("--symbol", required=True)
    parser.add_argument(
        "--storage-root",
        type=Path,
        required=True,
        metavar="ABSOLUTE_OWNER_PRIVATE_ROOT",
    )
    parser.add_argument("--contract-version", choices=("v1",), required=True)
    parser.add_argument(
        "--question", choices=("PRICE_BEHAVIOR", "CURRENT_STRUCTURE"), required=True
    )
    parser.add_argument("--previous-selection-time", type=_instant, required=True)
    parser.add_argument("--current-selection-time", type=_instant, required=True)
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    observation_service: CurrentStockObservationPortV1 | None = None,
) -> int:
    try:
        args = _parser().parse_args(argv)
        if (
            not _valid_symbol(args.symbol)
            or not args.storage_root.is_absolute()
            or args.previous_selection_time >= args.current_selection_time
        ):
            raise ValueError("invalid comparison request")
    except (TypeError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2

    def observe(selection_time: datetime) -> CurrentStockResearchResultV2:
        if observation_service is not None:
            return observation_service(
                args.symbol,
                args.storage_root,
                question=args.question,
                selection_time=selection_time,
            )
        return research_current_stock_v2(
            args.symbol,
            args.storage_root,
            question=args.question,
            refresh=False,
            clock=_FixedClock(selection_time),
            calendar_transport=_RetainedOnlyTransport(),
            snapshot_transport=_RetainedOnlyTransport(),
            price_client=_RetainedOnlyPrices(),  # type: ignore[arg-type]
        )

    try:
        previous = observe(args.previous_selection_time)
        current = observe(args.current_selection_time)
        result = compare_current_stock_observations_v1(previous, current)
    except Exception:  # noqa: BLE001 - CLI boundary must fail closed without disclosure
        sys.stderr.write("observation_interrupted\n")
        try:
            result = invalid_current_stock_observation_comparison_v1()
        except Exception:  # noqa: BLE001 - invalid runtime cannot mint a trusted result
            sys.stderr.write("comparison_runtime_invalid\n")
            return 1
    sys.stdout.buffer.write(result.canonical_json_bytes())
    return 0 if result.status == "COMPARABLE" else 1


__all__ = ["CurrentStockObservationPortV1", "main"]
