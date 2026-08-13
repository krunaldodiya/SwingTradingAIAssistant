"""Provider-free application for a sealed prospective readiness manifest."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, cast

from swing_trading_ai_assistant.market_data.schedule_evidence import (
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
)
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50UniverseSnapshotV1,
)

from .prospective_readiness import (
    PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
    PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
    DeclarationReceiptV1,
    EvidenceAuthorityV1,
    EvidenceClassV1,
    ProspectiveReadinessReportV1,
    ProspectiveReadinessRequestV1,
    ScheduleEvidenceCandidateV1,
    SourceReceiptV1,
    UniverseEvidenceCandidateV1,
    evaluate_prospective_readiness_v1,
)

PROSPECTIVE_MANIFEST_CONTRACT_VERSION_V1: Final = (
    "retained-prospective-evidence-manifest@v1"
)
_RETAINED_SEAL_SHA256: Final = (
    "3c0450aa4885dcfbf7f1e94673a2b4fec402b184dd7d224d849b4a44e537d809"
)
_RETAINED_UNIVERSE_SHA256: Final = (
    "936a32c8dee5d852221a159434064be79380fe75a40029c1e0b506c0086e0b30"
)
_RETAINED_SCHEDULE_SHA256: Final = frozenset(
    {
        "09f7e6b8477d4588668957f3d063acd3982d4cb7c7f1ebcde49f3dbc496e5930",
        "7c8cdef86c3874f9542a9544821805bfc23787975e29d0f297164776b5816db9",
    }
)
_RETAINED_COVERAGE_SHA256: Final = (
    "ee0425ecbe7e4a269b40f92a895023d7b75a986531d1b9638403e8382e3a2fab"
)
_MAX_SEAL_BYTES: Final = 128 * 1024
_MAX_UNIVERSE_BYTES: Final = 64 * 1024
_MAX_SCHEDULE_BYTES: Final = 1024 * 1024
_MAX_COVERAGE_BYTES: Final = 128 * 1024
_LICENCE_REVIEW_SHA256: Final = hashlib.sha256(
    b"prospective retained evidence licence review pending@v1"
).hexdigest()
_WARNINGS: Final = (
    (
        "NO_READINESS_MANUFACTURED",
        "Retained gaps and late evidence remain blocking outcomes in the embedded report.",
    ),
    (
        "NO_NETWORK_PROVIDER_OR_ENVIRONMENT_INPUT",
        "This manifest uses only the four explicit retained-evidence path roles.",
    ),
    (
        "NO_RAW_OHLC_OR_BROKER_BEHAVIOR",
        "This application reads no price bars and performs no broker action.",
    ),
    (
        "UPSTOX_IS_CURRENT_MARKET_DATA_PROVIDER_NOT_PORTFOLIO_OR_ORDER_AUTHORITY",
        "The retained provider role establishes neither portfolio nor broker authority.",
    ),
    (
        "READ_ONLY_PORTFOLIO_AND_FUTURE_ORDER_CONNECTORS_ARE_SEPARATE_BROKER_AGNOSTIC_BOUNDARIES",
        "Connector boundaries remain outside this evidence-readiness application.",
    ),
    (
        "NO_TRADING_OR_PERFORMANCE_CLAIM",
        "Readiness is not a trade recommendation, prediction, or profitability claim.",
    ),
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _bounded_regular_file(path: Path, maximum: int) -> bytes:
    """Read one bounded regular file without following its final symlink."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise ValueError("no-follow file reads unavailable")
    descriptor = os.open(path, flags | nofollow)
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_size < 1
            or details.st_size > maximum
        ):
            raise ValueError("inadmissible retained evidence file")
        chunks: list[bytes] = []
        remaining = details.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("truncated retained evidence file")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("retained evidence file changed during read")
        after = os.fstat(descriptor)
        if (
            after.st_dev != details.st_dev
            or after.st_ino != details.st_ino
            or after.st_size != details.st_size
        ):
            raise ValueError("retained evidence file changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _json_object(raw: bytes) -> dict[str, object]:
    value: object = json.loads(raw)
    if type(value) is not dict:
        raise ValueError("retained evidence is not an object")
    return cast(dict[str, object], value)


def _is_path(value: object) -> bool:
    return isinstance(value, Path)


@dataclass(frozen=True, slots=True)
class RetainedReadinessManifestRequestV1:
    seal_path: Path
    universe_path: Path
    schedule_paths: tuple[Path, ...]
    coverage_manifest_path: Path
    cohort_id: str
    declared_at: datetime
    declaration_retained_at: datetime
    decision_session: date
    evaluated_at: datetime
    validation_policy_sha256: str
    configuration_sha256: str
    code_identity: str
    sprint4_seal_sha256: str = _RETAINED_SEAL_SHA256

    def __post_init__(self) -> None:
        digests = (self.validation_policy_sha256, self.configuration_sha256)
        if (
            not _is_path(self.seal_path)
            or not _is_path(self.universe_path)
            or not _is_path(self.coverage_manifest_path)
            or type(self.schedule_paths) is not tuple
            or len(self.schedule_paths) != 2
            or any(not _is_path(path) for path in self.schedule_paths)
            or len(set(self.schedule_paths)) != 2
            or len({self.seal_path, self.universe_path, self.coverage_manifest_path, *self.schedule_paths}) != 5
            or type(self.cohort_id) is not str
            or not self.cohort_id
            or type(self.declared_at) is not datetime
            or self.declared_at.tzinfo is None
            or type(self.declaration_retained_at) is not datetime
            or self.declaration_retained_at.tzinfo is None
            or self.declaration_retained_at < self.declared_at
            or type(self.decision_session) is not date
            or type(self.evaluated_at) is not datetime
            or self.evaluated_at.tzinfo is None
            or self.evaluated_at <= self.declaration_retained_at
            or any(
                type(value) is not str
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in digests
            )
            or type(self.code_identity) is not str
            or not self.code_identity
            or self.sprint4_seal_sha256 != _RETAINED_SEAL_SHA256
        ):
            raise ValueError("invalid retained readiness manifest request")


ProspectiveManifestRequestV1 = RetainedReadinessManifestRequestV1


@dataclass(frozen=True, slots=True)
class ProspectiveEvidenceManifestV1:
    report: ProspectiveReadinessReportV1
    cohort_id: str
    declared_at: datetime
    declaration_retained_at: datetime
    evaluated_at: datetime
    decision_session: date
    seal_sha256: str
    universe_sha256: str
    schedule_sha256: tuple[str, ...]
    coverage_sha256: str
    warnings: tuple[tuple[str, str], ...] = _WARNINGS
    provider_attempts: int = 0
    network_attempts: int = 0
    storage_write_attempts: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.report) is not ProspectiveReadinessReportV1
            or len(self.report.rows) != 50
            or self.seal_sha256 != _RETAINED_SEAL_SHA256
            or self.universe_sha256 != _RETAINED_UNIVERSE_SHA256
            or frozenset(self.schedule_sha256) != _RETAINED_SCHEDULE_SHA256
            or len(self.schedule_sha256) != 2
            or self.coverage_sha256 != _RETAINED_COVERAGE_SHA256
            or self.warnings != _WARNINGS
            or any(
                value != 0
                for value in (
                    self.provider_attempts,
                    self.network_attempts,
                    self.storage_write_attempts,
                    self.report.provider_attempts,
                    self.report.network_attempts,
                    self.report.storage_write_attempts,
                )
            )
        ):
            raise ValueError("invalid prospective evidence manifest")

    @property
    def manifest_identity_sha256(self) -> str:
        return _sha(_canonical(_manifest_value(self, include_identity=False)))

    def canonical_json_bytes(self) -> bytes:
        return _canonical(_manifest_value(self, include_identity=True))


def _manifest_value(
    value: ProspectiveEvidenceManifestV1, *, include_identity: bool
) -> dict[str, object]:
    report_value = cast(
        dict[str, object], json.loads(value.report.canonical_json_bytes())
    )
    result: dict[str, object] = {
        "classification": "PROSPECTIVE_EVIDENCE_READINESS_ONLY",
        "cohort_id": value.cohort_id,
        "contract_version": PROSPECTIVE_MANIFEST_CONTRACT_VERSION_V1,
        "coverage_sha256": value.coverage_sha256,
        "decision_session": value.decision_session.isoformat(),
        "declaration": {
            "declared_at": _timestamp(value.declared_at),
            "retained_at": _timestamp(value.declaration_retained_at),
        },
        "evaluated_at": _timestamp(value.evaluated_at),
        "network_attempts": value.network_attempts,
        "provider_attempts": value.provider_attempts,
        "sprint4_result": {
            "eligible_pairs": 0,
            "insufficient_pairs": 1550,
            "requested_pairs": 1550,
            "result_is_immutable": True,
        },
        "readiness_report": report_value,
        "schedule_sha256": list(value.schedule_sha256),
        "seal_sha256": value.seal_sha256,
        "storage_write_attempts": value.storage_write_attempts,
        "universe_sha256": value.universe_sha256,
        "warnings": [
            {"code": code, "message": message} for code, message in value.warnings
        ],
    }
    if include_identity:
        result["manifest_identity_sha256"] = value.manifest_identity_sha256
    return result


def _source_receipt(
    *,
    evidence_class: EvidenceClassV1,
    authority: EvidenceAuthorityV1,
    payload: bytes,
    release: str,
    public_at: datetime,
    retained_at: datetime,
    clock_sha256: str,
    effective_from: date,
    effective_to: date,
    publication_proof_sha256: str,
) -> SourceReceiptV1:
    return SourceReceiptV1(
        evidence_class=evidence_class,
        authority=authority,
        release_identity=release,
        source_bytes_sha256=_sha(payload),
        publication_proof_sha256=publication_proof_sha256,
        public_available_at=public_at,
        request_started_at=retained_at,
        response_completed_at=retained_at,
        retained_at=retained_at,
        trusted_clock_identity_sha256=clock_sha256,
        effective_from=effective_from,
        effective_to=effective_to,
        revision_identity=release,
        supersedes_revision_identity=None,
        licence_review_identity_sha256=_LICENCE_REVIEW_SHA256,
    )


class ProspectiveManifestServiceV1:
    """Validate pinned retained artifacts and run the pure ARK-163 reducer."""

    def run(
        self, request: ProspectiveManifestRequestV1
    ) -> ProspectiveEvidenceManifestV1:
        try:
            return self._run(request)
        except Exception:
            raise ValueError("prospective evidence manifest unavailable") from None

    def _run(
        self, request: ProspectiveManifestRequestV1
    ) -> ProspectiveEvidenceManifestV1:
        if type(request) is not RetainedReadinessManifestRequestV1:
            raise ValueError
        seal_raw = _bounded_regular_file(request.seal_path, _MAX_SEAL_BYTES)
        universe_raw = _bounded_regular_file(request.universe_path, _MAX_UNIVERSE_BYTES)
        if (
            type(request.schedule_paths) is not tuple
            or len(request.schedule_paths) != 2
        ):
            raise ValueError
        schedule_raw = tuple(
            _bounded_regular_file(path, _MAX_SCHEDULE_BYTES)
            for path in request.schedule_paths
        )
        coverage_raw = _bounded_regular_file(request.coverage_manifest_path, _MAX_COVERAGE_BYTES)
        schedule_digests = tuple(sorted(_sha(raw) for raw in schedule_raw))
        if (
            request.sprint4_seal_sha256 != _RETAINED_SEAL_SHA256
            or _sha(seal_raw) != _RETAINED_SEAL_SHA256
            or _sha(universe_raw) != _RETAINED_UNIVERSE_SHA256
            or frozenset(schedule_digests) != _RETAINED_SCHEDULE_SHA256
            or len(set(schedule_digests)) != 2
            or _sha(coverage_raw) != _RETAINED_COVERAGE_SHA256
        ):
            raise ValueError
        seal = _json_object(seal_raw)
        coverage = _json_object(coverage_raw)
        seal_schedules = seal.get("schedule_digests_sha256")
        source = seal.get("source_evidence")
        if type(source) is not dict:
            raise ValueError
        source_object = cast(dict[str, object], source)
        if (
            seal.get("contract_version") != "retained-nifty50-evidence-seal-v1"
            or seal.get("provider_attempt_count") != 0
            or seal.get("stock_count") != 50
            or seal.get("universe_snapshot_sha256") != _RETAINED_UNIVERSE_SHA256
            or type(seal_schedules) is not list
            or tuple(sorted(cast(list[str], seal_schedules))) != schedule_digests
            or source_object.get("bounded_coverage_report_sha256")
            != _RETAINED_COVERAGE_SHA256
            or coverage.get("provider_attempt_count") != 0
        ):
            raise ValueError
        universe = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(universe_raw)
        if (
            universe.canonical_json_bytes() != universe_raw
            or len(universe.constituents) != 50
        ):
            raise ValueError
        schedules = tuple(parse_canonical_schedule_bytes(raw) for raw in schedule_raw)
        if any(
            canonical_schedule_bytes(schedule) != raw
            for schedule, raw in zip(schedules, schedule_raw, strict=True)
        ):
            raise ValueError
        applicable = tuple(
            (schedule, raw)
            for schedule, raw in zip(schedules, schedule_raw, strict=True)
            if any(
                item.trade_date == request.decision_session
                for item in schedule.sessions
            )
        )
        if len(applicable) != 1:
            raise ValueError
        selected_schedule, selected_schedule_raw = applicable[0]
        declaration = DeclarationReceiptV1(
            request.declared_at,
            request.declaration_retained_at,
            _RETAINED_SEAL_SHA256,
        )
        membership_receipt = _source_receipt(
            evidence_class=EvidenceClassV1.MEMBERSHIP,
            authority=EvidenceAuthorityV1.NSE_INDICES_LIMITED,
            payload=universe_raw,
            release=universe.membership_release,
            public_at=universe.membership_published_at,
            retained_at=universe.membership_retrieved_at,
            clock_sha256=_RETAINED_SEAL_SHA256,
            effective_from=universe.effective_from,
            effective_to=universe.effective_to,
            publication_proof_sha256=_RETAINED_SEAL_SHA256,
        )
        sector_receipt = _source_receipt(
            evidence_class=EvidenceClassV1.SECTOR,
            authority=EvidenceAuthorityV1.NSE_INDICES_LIMITED,
            payload=universe_raw,
            release=universe.sector_release,
            public_at=universe.sector_published_at,
            retained_at=universe.sector_retrieved_at,
            clock_sha256=_RETAINED_SEAL_SHA256,
            effective_from=universe.effective_from,
            effective_to=universe.effective_to,
            publication_proof_sha256=_RETAINED_SEAL_SHA256,
        )
        schedule_receipt = _source_receipt(
            evidence_class=EvidenceClassV1.SCHEDULE,
            authority=EvidenceAuthorityV1.NSE_CAPITAL_MARKET,
            payload=selected_schedule_raw,
            release=selected_schedule.source_release,
            public_at=selected_schedule.as_of,
            retained_at=selected_schedule.as_of,
            clock_sha256=_RETAINED_SEAL_SHA256,
            effective_from=selected_schedule.covered_from,
            effective_to=selected_schedule.covered_to,
            publication_proof_sha256=_sha(selected_schedule_raw),
        )
        reducer_request = ProspectiveReadinessRequestV1(
            contract_version=PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
            source_policy_version=PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
            cohort_id=request.cohort_id,
            declaration_receipt=declaration,
            decision_session=request.decision_session,
            evaluated_at=request.evaluated_at,
            required_isins=tuple(item.isin for item in universe.constituents),
            trusted_universe_snapshot_sha256=_RETAINED_UNIVERSE_SHA256,
            validation_policy_sha256=request.validation_policy_sha256,
            configuration_sha256=request.configuration_sha256,
            code_identity=request.code_identity,
            sprint4_seal_sha256=_RETAINED_SEAL_SHA256,
            universe_candidates=(
                UniverseEvidenceCandidateV1(
                    universe_raw, membership_receipt, sector_receipt
                ),
            ),
            schedule_candidates=(
                ScheduleEvidenceCandidateV1(selected_schedule_raw, schedule_receipt),
            ),
        )
        report = evaluate_prospective_readiness_v1(reducer_request)
        return ProspectiveEvidenceManifestV1(
            report=report,
            cohort_id=request.cohort_id,
            declared_at=declaration.declared_at,
            declaration_retained_at=declaration.retained_at,
            evaluated_at=request.evaluated_at.astimezone(UTC),
            decision_session=request.decision_session,
            seal_sha256=_RETAINED_SEAL_SHA256,
            universe_sha256=_RETAINED_UNIVERSE_SHA256,
            schedule_sha256=schedule_digests,
            coverage_sha256=_RETAINED_COVERAGE_SHA256,
        )


RetainedReadinessManifestServiceV1 = ProspectiveManifestServiceV1
EvidenceReadinessManifestRequestV1 = RetainedReadinessManifestRequestV1
EvidenceReadinessManifestServiceV1 = RetainedReadinessManifestServiceV1

__all__ = [
    "PROSPECTIVE_MANIFEST_CONTRACT_VERSION_V1",
    "EvidenceReadinessManifestRequestV1",
    "EvidenceReadinessManifestServiceV1",
    "ProspectiveEvidenceManifestV1",
    "ProspectiveManifestRequestV1",
    "ProspectiveManifestServiceV1",
    "RetainedReadinessManifestRequestV1",
    "RetainedReadinessManifestServiceV1",
]
