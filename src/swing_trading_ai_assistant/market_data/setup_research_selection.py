"""Bounded whole-selection orchestration of unchanged same-observation research."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from .agent_research_run import ResearchService, validate_agent_research_request
from .agent_setup_research import run_agent_setup_research_current
from .bharatstock import BharatStockInstrument
from .bharatstock_capture import (
    CaptureRequestV2,
    selection_identity_v2,
    validate_current_capture_request_v2,
)
from .current_stock_research import CurrentStockResearchInputError
from .efficient_current_nifty100_adjusted_capture import (
    SelectionEvidenceUnavailable,
    read_retained_current_nifty100_selection_v1,
)
from .runtime_source_verifier import runtime_source_sha256
from .setup_research_selection_runtime_identity_manifest import (
    SETUP_RESEARCH_SELECTION_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_screen import (
    _bytes,  # pyright: ignore[reportPrivateUsage]
    _identity,  # pyright: ignore[reportPrivateUsage]
)

MAX_SELECTION_OUTPUT_BYTES = 11 * 1024 * 1024
_RUNTIME_SOURCES = tuple(
    f"src/swing_trading_ai_assistant/market_data/{name}.py"
    for name in (
        "setup_research_selection",
        "agent_setup_research",
        "agent_setup_research_runtime_identity_manifest",
        "cli",
        "efficient_current_nifty100_adjusted_capture",
        "bharatstock_capture",
        "bharatstock_capture_runtime_identity_manifest",
        "runtime_source_verifier",
    )
) + (
    "src/swing_trading_ai_assistant/historical_evaluation/capability_validation_cli.py",
)
_LIMITATIONS = (
    "Default Nifty100 selection is exact at retained witness retrieval; explicit symbols carry no official membership claim, and neither mode claims latest-today or earlier historical membership.",
    "Independent current stock observations have no shared acquisition cutoff; selector capture cutoff is not research cutoff.",
    "Whole-list comparison repeats existing descriptive predicates; no cohort metrics, averaging, ranking or eligibility inference.",
    "Research and detection only; recommendation, active signal policy, AI quality and market effectiveness are not assessed.",
    "Owner-private source evidence; no external AI destination or disclosure authority is granted.",
)


def _runtime_identity() -> str:
    if tuple(SETUP_RESEARCH_SELECTION_RUNTIME_SOURCE_SHA256_V1) != _RUNTIME_SOURCES:
        raise ValueError("selection research runtime scope invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in SETUP_RESEARCH_SELECTION_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("selection research runtime identity invalid")
        observed[relative] = actual
    return _identity(observed)


def _validate_symbol_selection(symbols: tuple[str, ...], storage_root: Path) -> None:
    if type(symbols) is not tuple or not 1 <= len(symbols) <= 100:
        raise CurrentStockResearchInputError("invalid symbol selection")
    for offset in range(0, len(symbols), 10):
        validate_agent_research_request(symbols[offset : offset + 10], storage_root)
    if len(set(symbols)) != len(symbols):
        raise CurrentStockResearchInputError("duplicate symbol selection")


def _selection(
    symbols: tuple[str, ...] | None,
    storage_root: Path,
    request: CaptureRequestV2 | None,
    root: Path | None,
    clock: Callable[[], datetime] | None,
) -> tuple[tuple[str, ...], tuple[BharatStockInstrument, ...], dict[str, object]]:
    if (
        not isinstance(storage_root, Path)  # pyright: ignore[reportUnnecessaryIsInstance]
        or not storage_root.is_absolute()
    ):
        raise CurrentStockResearchInputError("invalid selection research root")
    if symbols is not None:
        if request is not None or root is not None:
            raise CurrentStockResearchInputError("invalid explicit selection")
        _validate_symbol_selection(symbols, storage_root)
        return (
            symbols,
            (),
            {
                "kind": "EXPLICIT_SYMBOLS",
                "contract_version": "explicit-research-symbol-selection@v1",
                "knowledge_basis": "CALLER_SUPPLIED_SYMBOLS",
                "known_at": None,
                "source_identity_sha256": None,
                "capture_request_identity_sha256": None,
                "selection_identity_sha256": None,
                "expected_members": None,
            },
        )
    if type(request) is not CaptureRequestV2 or not isinstance(root, Path):
        raise CurrentStockResearchInputError("invalid default selection")
    now = datetime.now(UTC) if clock is None else clock()
    if type(now) is not datetime or now.tzinfo is None:
        raise CurrentStockResearchInputError("invalid selection clock")
    try:
        validate_current_capture_request_v2(request)
        _validate_symbol_selection(
            tuple(member.symbol for member in request.members), storage_root
        )
        selected = read_retained_current_nifty100_selection_v1(
            root, request, known_at=now
        )
    except ValueError as error:
        if isinstance(error, SelectionEvidenceUnavailable):
            raise
        raise CurrentStockResearchInputError("invalid default selection") from None
    return (
        tuple(member.symbol for member in selected.members),
        selected.members,
        {
            "kind": "RETAINED_NIFTY100",
            "contract_version": "retained-current-nifty100-selection@v1",
            "knowledge_basis": "CURRENT_AT_RETRIEVAL",
            "known_at": selected.retrieved_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "source_identity_sha256": selected.source_identity_sha256,
            "capture_request_identity_sha256": request.request_identity_sha256,
            "selection_identity_sha256": selected.selection_identity_sha256,
            "expected_members": [
                {
                    "isin": member.isin,
                    "exchange": member.exchange,
                    "effective_symbol": member.symbol,
                }
                for member in selected.members
            ],
        },
    )


def _comparison(
    session: object, basis: object, schedule: object, profile: object
) -> tuple[str, str, str, str] | None:
    if all(type(value) is str for value in (session, basis, schedule, profile)):
        return cast(tuple[str, str, str, str], (session, basis, schedule, profile))
    return None


def _joint(values: list[tuple[str, str, str, str] | None]) -> bool:
    return bool(values) and None not in values and len(set(values)) == 1


def _global_facts(
    reports: list[dict[str, object]],
    symbols: tuple[str, ...],
    selected: tuple[BharatStockInstrument, ...],
) -> tuple[str | None, bool, bool]:
    rows = [
        row
        for child in reports
        for row in cast(list[dict[str, object]], child["members"])
    ]
    if tuple(row["requested_symbol"] for row in rows) != symbols:
        raise ValueError("selection research member order invalid")
    canonical: list[BharatStockInstrument] = []
    candidate_comparisons: list[tuple[str, str, str, str] | None] = []
    for position, row in enumerate(rows):
        mapping = cast(dict[str, str] | None, row["canonical_stock"])
        if mapping is not None:
            instrument = BharatStockInstrument(
                mapping["isin"], mapping["exchange"], mapping["effective_symbol"]
            )
            if selected and instrument != selected[position]:
                raise ValueError("selected canonical research member mismatch")
            canonical.append(instrument)
        candidate_comparisons.append(
            _comparison(
                row["session"],
                row["price_basis"],
                row["schedule_identity_sha256"],
                row["source_profile"],
            )
        )
    if len({(member.isin, member.exchange) for member in canonical}) != len(canonical):
        raise CurrentStockResearchInputError("duplicate canonical selection member")
    base_comparisons: list[tuple[str, str, str, str] | None] = []
    for child in reports:
        base = cast(dict[str, object], child["research"])
        for row in cast(list[dict[str, object]], base["members"]):
            for feature in cast(dict[str, dict[str, object]], row["features"]).values():
                fact = cast(dict[str, object] | None, feature["fact"])
                base_comparisons.append(
                    None
                    if fact is None
                    else _comparison(
                        fact["session"],
                        row["price_basis"],
                        feature["schedule_identity_sha256"],
                        feature["source_profile"],
                    )
                )
    return (
        selection_identity_v2(tuple(canonical))
        if len(canonical) == len(symbols)
        else None,
        _joint(base_comparisons),
        _joint(candidate_comparisons),
    )


def selection_research_available(report: dict[str, object]) -> bool:
    """Availability is the unchanged per-member G01 scope, never trade approval."""
    for child in cast(list[dict[str, object]], report["reports"]):
        if any(
            row["status"] == "UNKNOWN"
            for row in cast(list[dict[str, object]], child["members"])
        ):
            return False
        base = cast(dict[str, object], child["research"])
        if any(
            feature["fact"] is None
            for row in cast(list[dict[str, object]], base["members"])
            for feature in cast(dict[str, dict[str, object]], row["features"]).values()
        ):
            return False
    return True


def run_setup_research_selection_current(
    symbols: tuple[str, ...] | None,
    storage_root: Path,
    *,
    research: ResearchService,
    selection_request: CaptureRequestV2 | None = None,
    selection_root: Path | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Research one exact bounded selection; no new source, store or trade policy."""
    symbols, selected, selection = _selection(
        symbols, storage_root, selection_request, selection_root, clock
    )
    runtime = _runtime_identity()
    reports = [
        run_agent_setup_research_current(
            symbols[offset : offset + 10], storage_root, research=research
        )
        for offset in range(0, len(symbols), 10)
    ]
    canonical, base_comparable, candidate_comparable = _global_facts(
        reports, symbols, selected
    )
    report: dict[str, object] = {
        "contract_version": "agent-current-setup-research-selection@v1",
        "runtime_code_identity_sha256": runtime,
        "selection": selection,
        "requested_order_identity_sha256": _identity(list(symbols)),
        "canonical_order_identity_sha256": canonical,
        "reports": reports,
        "research_jointly_comparable": base_comparable,
        "candidate_jointly_comparable": candidate_comparable,
        "limitations": list(_LIMITATIONS),
    }
    report["result_identity_sha256"] = _identity(report)
    if len(_bytes(report)) > MAX_SELECTION_OUTPUT_BYTES:
        raise ValueError("selection research output limit exceeded")
    return report
