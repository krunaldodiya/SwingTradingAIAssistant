"""Provider-free retained-evidence adapter for the strict historical census."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from .census import OpportunityCensusReportV1, build_strict_retained_census_v1


@dataclass(frozen=True, slots=True)
class RetainedCensusRequestV1:
    seal_path: Path
    evidence_seal_sha256: str
    universe_path: Path
    schedule_paths: tuple[Path, ...]
    data_manifest_path: Path
    observation_cutoff: datetime
    code_sha: str
    configuration_sha256: str


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class RetainedCensusServiceV1:
    """Deeply validate an immutable seal and reduce its strict PIT result."""

    def run(  # noqa: C901 -- one fail-closed validation transaction
        self, request: RetainedCensusRequestV1
    ) -> OpportunityCensusReportV1:
        try:
            raw = request.seal_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != request.evidence_seal_sha256:
                raise ValueError
            parsed: object = json.loads(raw)
            if type(parsed) is not dict:
                raise ValueError
            seal = cast(dict[str, object], parsed)
            universe_bytes = request.universe_path.read_bytes()
            universe_parsed: object = json.loads(universe_bytes)
            schedule_bytes = tuple(path.read_bytes() for path in request.schedule_paths)
            schedule_parsed = tuple(json.loads(value) for value in schedule_bytes)
            data_manifest_bytes = request.data_manifest_path.read_bytes()
            data_manifest_parsed: object = json.loads(data_manifest_bytes)
            selections_raw = seal.get("selections")
            schedules_raw = seal.get("schedule_digests_sha256")
            source_raw = seal.get("source_evidence")
            if (
                type(selections_raw) is not list
                or type(schedules_raw) is not list
                or type(source_raw) is not dict
            ):
                raise ValueError
            selections = cast(list[object], selections_raw)
            schedules = cast(list[object], schedules_raw)
            source = cast(dict[str, object], source_raw)
            identity_keys = (
                "contract_version",
                "code_commit",
                "knowledge_cutoff",
                "requested_from",
                "requested_to",
                "universe_snapshot_sha256",
                "schedule_digests_sha256",
                "selections",
            )
            identity = {key: seal.get(key) for key in identity_keys}
            if (
                seal.get("contract_version") != "retained-nifty50-evidence-seal-v1"
                or seal.get("classification") != "EXPLORATORY_DEVELOPMENT_EVIDENCE_ONLY"
                or seal.get("status")
                != "SEALED_PROVIDER_FREE_WITH_DECLARED_CATALOG_LIMITATION"
                or seal.get("provider_attempt_count") != 0
                or seal.get("stock_count") != 50
                or seal.get("partition_count") != 100
                or seal.get("dataset_identity_sha256") != _digest(identity)
                or len(selections) != 100
                or len(schedules) != 2
            ):
                raise ValueError
            pairs: set[tuple[str, str]] = set()
            identities: set[tuple[str, str]] = set()
            candle_digests: set[str] = set()
            for raw_item in selections:
                if type(raw_item) is not dict:
                    raise ValueError
                item = cast(dict[str, object], raw_item)
                isin, symbol, month = (
                    item.get("isin"),
                    item.get("symbol"),
                    item.get("month"),
                )
                checksum, schedule = (
                    item.get("checksum_sha256"),
                    item.get("schedule_digest_sha256"),
                )
                if not all(
                    type(value) is str
                    for value in (isin, symbol, month, checksum, schedule)
                ):
                    raise ValueError
                pairs.add((cast(str, isin), cast(str, month)))
                identities.add((cast(str, isin), cast(str, symbol)))
                candle_digests.add(cast(str, checksum))
                if (
                    schedule not in schedules
                    or item.get("row_count") not in (3000, 8625)
                    or item.get("adjustment_state") != "raw"
                ):
                    raise ValueError
            if (
                len(pairs) != 100
                or len(identities) != 50
                or any(
                    sum(pair[0] == isin for pair in pairs) != 2
                    for isin, _ in identities
                )
            ):
                raise ValueError
            universe_digest = seal.get("universe_snapshot_sha256")
            if type(universe_digest) is not str or any(
                type(value) is not str for value in schedules
            ):
                raise ValueError
            data_manifest = source.get("bounded_coverage_report_sha256")
            if (
                type(data_manifest) is not str
                or hashlib.sha256(universe_bytes).hexdigest() != universe_digest
                or tuple(
                    sorted(
                        hashlib.sha256(value).hexdigest() for value in schedule_bytes
                    )
                )
                != tuple(sorted(cast(list[str], schedules)))
                or hashlib.sha256(data_manifest_bytes).hexdigest() != data_manifest
                or type(universe_parsed) is not dict
                or type(data_manifest_parsed) is not dict
                or any(type(value) is not dict for value in schedule_parsed)
            ):
                raise ValueError
            universe_value = cast(dict[str, object], universe_parsed)
            manifest_value = cast(dict[str, object], data_manifest_parsed)
            schedule_values = tuple(
                cast(dict[str, object], value) for value in schedule_parsed
            )
            raw_constituents = universe_value.get("constituents")
            raw_results = manifest_value.get("results")
            if type(raw_constituents) is not list or type(raw_results) is not list:
                raise ValueError
            universe_identities: set[tuple[str, str]] = set()
            for raw_member in cast(list[object], raw_constituents):
                if type(raw_member) is not dict:
                    raise ValueError
                member = cast(dict[str, object], raw_member)
                isin, symbol = member.get("isin"), member.get("symbol")
                if type(isin) is not str or type(symbol) is not str:
                    raise ValueError
                universe_identities.add((isin, symbol))
            manifest_symbols: set[str] = set()
            for raw_result in cast(list[object], raw_results):
                if type(raw_result) is not dict:
                    raise ValueError
                symbol = cast(dict[str, object], raw_result).get("symbol")
                if type(symbol) is not str:
                    raise ValueError
                manifest_symbols.add(symbol)
            official_dates: list[date] = []
            for schedule_value in schedule_values:
                raw_sessions = schedule_value.get("sessions")
                if (
                    type(raw_sessions) is not list
                    or type(schedule_value.get("as_of")) is not str
                ):
                    raise ValueError
                for raw_session in cast(list[object], raw_sessions):
                    if type(raw_session) is not dict:
                        raise ValueError
                    session = cast(dict[str, object], raw_session)
                    trade_date = session.get("trade_date")
                    open_at = session.get("open_at")
                    close_at = session.get("close_at")
                    if (
                        type(trade_date) is not str
                        or type(open_at) is not str
                        or type(close_at) is not str
                    ):
                        raise ValueError
                    day = date.fromisoformat(trade_date)
                    if not (_timestamp(open_at) < _timestamp(close_at)):
                        raise ValueError
                    official_dates.append(day)
            if (
                len(universe_identities) != 50
                or identities != universe_identities
                or manifest_symbols != {symbol for _, symbol in identities}
                or manifest_value.get("provider_attempt_count") != 0
                or _timestamp(universe_value.get("membership_retrieved_at"))
                != datetime(2026, 8, 12, 8, 56, 38, 181171, tzinfo=UTC)
                or tuple(sorted(set(official_dates))) != tuple(official_dates)
                or len(official_dates) != 31
            ):
                raise ValueError
            cutoff = request.observation_cutoff.astimezone(UTC)
            if _timestamp(seal.get("knowledge_cutoff")) > cutoff:
                raise ValueError
            sessions = tuple(official_dates)
            return build_strict_retained_census_v1(
                stock_count=50,
                decision_sessions=sessions,
                universe_known_at=datetime(2026, 8, 12, 8, 56, 38, 181171, tzinfo=UTC),
                corporate_action_evidence_available=False,
                evidence_seal_sha256=request.evidence_seal_sha256,
                data_manifest_sha256=data_manifest,
                universe_evidence_sha256=(universe_digest,),
                schedule_evidence_sha256=tuple(sorted(cast(list[str], schedules))),
                candle_evidence_sha256=tuple(sorted(candle_digests)),
                corporate_action_evidence_sha256=(),
                observation_cutoff=cutoff,
                code_sha=request.code_sha,
                configuration_sha256=request.configuration_sha256,
            )
        except Exception:
            raise ValueError("retained census evidence unavailable") from None
