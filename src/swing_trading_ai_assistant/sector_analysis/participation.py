"""Pure owner-private aggregation of observed member directions by opaque label."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import cast

from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50UniverseSnapshotV1,
    ResolvedNifty50UniverseSnapshotV1,
    UniverseSnapshotAmbiguousError,
    UniverseSnapshotCorruptError,
    UniverseSnapshotMetadataV1,
    UniverseSnapshotNotFoundError,
    UniverseSnapshotStaleError,
)
from swing_trading_ai_assistant.market_regime.boundary import (
    canonical_json_lf,
    validate_local_date,
    validate_sha256,
    validate_utc_instant,
)
from swing_trading_ai_assistant.market_regime.facts import VerifiedMarketRegimeFactsV1
from swing_trading_ai_assistant.market_regime.observed import (
    MarketRegimeReportV1,
    _MarketRegimeSectorHandoffV1,  # pyright: ignore[reportPrivateUsage]
    _reduce_observed_market_regime_with_sector_handoff_v1,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_regime.reducer import (
    MarketRegimeInsufficiencyV1,
)

__all__ = [
    "SectorCountV1",
    "SectorParticipationInsufficiencyV1",
    "SectorParticipationReasonV1",
    "SectorParticipationReportV1",
    "reduce_sector_participation_v1",
]

_SAFE_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .&()/_-]{0,63}\Z")
_MAX_REPORT_BYTES = 65_536


class SectorParticipationReasonV1(StrEnum):
    """Closed fail-closed reasons in global precedence order."""

    MARKET_REGIME_UNAVAILABLE = "MARKET_REGIME_UNAVAILABLE"
    SECTOR_CLASSIFICATION_MISSING = "SECTOR_CLASSIFICATION_MISSING"
    SECTOR_CLASSIFICATION_STALE = "SECTOR_CLASSIFICATION_STALE"
    SECTOR_CLASSIFICATION_AMBIGUOUS = "SECTOR_CLASSIFICATION_AMBIGUOUS"
    SECTOR_CLASSIFICATION_CORRUPT = "SECTOR_CLASSIFICATION_CORRUPT"
    SECTOR_EFFECTIVE_SCOPE_MISMATCH = "SECTOR_EFFECTIVE_SCOPE_MISMATCH"
    EVIDENCE_CUTOFF_MISMATCH = "EVIDENCE_CUTOFF_MISMATCH"
    MEMBER_IDENTITY_MISMATCH = "MEMBER_IDENTITY_MISMATCH"


@dataclass(frozen=True, slots=True)
class SectorParticipationInsufficiencyV1:
    """Whole-result insufficiency with no sector or upstream detail."""

    evidence_state: str
    sectors: None
    primary_reason: SectorParticipationReasonV1
    additional_reasons: tuple[SectorParticipationReasonV1, ...]

    def __post_init__(self) -> None:
        if self.evidence_state != "INSUFFICIENT_EVIDENCE":
            raise ValueError("insufficiency state is fixed")
        if self.sectors is not None:
            raise ValueError("insufficiency sectors must be null")
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            self.primary_reason, SectorParticipationReasonV1
        ):
            raise TypeError("primary reason must be closed")
        if type(self.additional_reasons) is not tuple or any(
            not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
                reason, SectorParticipationReasonV1
            )
            for reason in self.additional_reasons
        ):
            raise TypeError("additional reasons must be an immutable closed tuple")
        combined = (self.primary_reason, *self.additional_reasons)
        ordered = tuple(
            reason for reason in SectorParticipationReasonV1 if reason in combined
        )
        if len(set(combined)) != len(combined) or combined != ordered:
            raise ValueError("reasons must be unique and declaration ordered")

    @classmethod
    def from_reasons(cls, reasons: object) -> SectorParticipationInsufficiencyV1:
        if isinstance(reasons, (str, bytes)) or not isinstance(reasons, Sequence):
            raise TypeError("reasons must be a sequence")
        copied = tuple(cast("Sequence[object]", reasons))
        if not copied:
            raise ValueError("insufficiency requires at least one reason")
        if any(
            not isinstance(reason, SectorParticipationReasonV1) for reason in copied
        ):
            raise TypeError("reasons must be closed")
        ordered = tuple(
            reason for reason in SectorParticipationReasonV1 if reason in copied
        )
        return cls(
            "INSUFFICIENT_EVIDENCE",
            None,
            ordered[0],
            ordered[1:],
        )


@dataclass(frozen=True, slots=True)
class SectorCountV1:
    """One canonical aggregate row keyed by an opaque source label."""

    label: str
    member_count: int
    advances: int
    declines: int
    unchanged: int

    def __post_init__(self) -> None:
        counts = (self.member_count, self.advances, self.declines, self.unchanged)
        if (
            type(self.label) is not str
            or _SAFE_LABEL.fullmatch(self.label) is None
            or any(type(value) is not int for value in counts)
            or not 1 <= self.member_count <= 50
            or any(not 0 <= value <= 50 for value in counts[1:])
            or self.member_count != sum(counts[1:])
        ):
            raise ValueError("invalid sector count")


@dataclass(frozen=True, slots=True)
class SectorParticipationReportV1:
    """Canonical aggregate-only owner-private sector participation report."""

    contract_version: str
    calculation_version: str
    request_identity_sha256: str
    market_regime_report_identity_sha256: str
    input_identity_sha256: str
    source_policy_identity_sha256: str
    validation_policy_identity_sha256: str
    privacy_policy_identity_sha256: str
    licence_policy_identity_sha256: str
    policy_identity_sha256: str
    code_identity_sha256: str
    decision_session: str
    comparison_session: str
    decision_market_close: str
    evidence_cutoff: str
    required_member_count: int
    evidence_state: str
    sectors: tuple[SectorCountV1, ...]
    primary_reason: None
    additional_reasons: tuple[()]
    report_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.contract_version != "nifty50-sector-participation@v1"
            or self.calculation_version != "nifty50-sector-participation-counter@v1"
            or self.required_member_count != 50
            or self.evidence_state != "OBSERVED"
        ):
            raise ValueError("invalid observed sector report constants")
        for identity in (
            self.request_identity_sha256,
            self.market_regime_report_identity_sha256,
            self.input_identity_sha256,
            self.source_policy_identity_sha256,
            self.validation_policy_identity_sha256,
            self.privacy_policy_identity_sha256,
            self.licence_policy_identity_sha256,
            self.policy_identity_sha256,
            self.code_identity_sha256,
            self.report_identity_sha256,
        ):
            validate_sha256(identity)
        validate_local_date(self.decision_session)
        validate_local_date(self.comparison_session)
        validate_utc_instant(self.decision_market_close)
        validate_utc_instant(self.evidence_cutoff)
        if self.decision_market_close >= self.evidence_cutoff:
            raise ValueError("decision close must precede evidence cutoff")
        if (
            type(self.sectors) is not tuple
            or not 1 <= len(self.sectors) <= 50
            or any(type(row) is not SectorCountV1 for row in self.sectors)
            or tuple(sorted(self.sectors, key=lambda row: row.label)) != self.sectors
            or len({row.label for row in self.sectors}) != len(self.sectors)
            or sum(row.member_count for row in self.sectors) != 50
        ):
            raise ValueError("invalid canonical sector rows")
        for row in self.sectors:
            row.__post_init__()
        if self.primary_reason is not None or self.additional_reasons != ():
            raise ValueError("observed sector report cannot carry reasons")
        expected_identity = hashlib.sha256(
            canonical_json_lf(self._identity_projection())
        ).hexdigest()
        if self.report_identity_sha256 != expected_identity:
            raise ValueError("sector report identity mismatch")

    def _identity_projection(self) -> dict[str, object]:
        return {
            "additional_reasons": [],
            "calculation_version": self.calculation_version,
            "code_identity_sha256": self.code_identity_sha256,
            "comparison_session": self.comparison_session,
            "contract_version": self.contract_version,
            "decision_market_close": self.decision_market_close,
            "decision_session": self.decision_session,
            "evidence_cutoff": self.evidence_cutoff,
            "evidence_state": self.evidence_state,
            "input_identity_sha256": self.input_identity_sha256,
            "licence_policy_identity_sha256": self.licence_policy_identity_sha256,
            "market_regime_report_identity_sha256": (
                self.market_regime_report_identity_sha256
            ),
            "policy_identity_sha256": self.policy_identity_sha256,
            "primary_reason": None,
            "privacy_policy_identity_sha256": self.privacy_policy_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "required_member_count": self.required_member_count,
            "sectors": self.sectors,
            "source_policy_identity_sha256": self.source_policy_identity_sha256,
            "validation_policy_identity_sha256": (
                self.validation_policy_identity_sha256
            ),
        }

    def canonical_json_bytes(self) -> bytes:
        raw = canonical_json_lf(self)
        if len(raw) > _MAX_REPORT_BYTES:
            raise ValueError("sector participation report exceeds 64 KiB")
        return raw


def reduce_sector_participation_v1(
    market_regime_facts_or_insufficiency: object,
    resolved_snapshot: object,
) -> SectorParticipationReportV1 | SectorParticipationInsufficiencyV1:
    """Reduce trusted upstream facts to one observed or whole-insufficient result."""
    report, handoff, metadata, snapshot = _admit_sector_participation_inputs(
        market_regime_facts_or_insufficiency,
        resolved_snapshot,
    )
    reasons, directions = _sector_participation_reasons(
        report,
        handoff,
        resolved_snapshot,
        snapshot,
    )
    if reasons:
        return SectorParticipationInsufficiencyV1.from_reasons(reasons)
    return _observed_sector_participation_report(
        cast(MarketRegimeReportV1, report),
        cast(_MarketRegimeSectorHandoffV1, handoff),
        cast(UniverseSnapshotMetadataV1, metadata),
        cast(Nifty50UniverseSnapshotV1, snapshot),
        cast(dict[str, str], directions),
    )


def _admit_sector_participation_inputs(
    market_regime_facts_or_insufficiency: object,
    resolved_snapshot: object,
) -> tuple[
    MarketRegimeReportV1 | None,
    _MarketRegimeSectorHandoffV1 | None,
    UniverseSnapshotMetadataV1 | None,
    Nifty50UniverseSnapshotV1 | None,
]:
    if market_regime_facts_or_insufficiency is not None and type(
        market_regime_facts_or_insufficiency
    ) not in (VerifiedMarketRegimeFactsV1, MarketRegimeInsufficiencyV1):
        raise TypeError("invalid market regime outcome")
    if resolved_snapshot is not None and type(resolved_snapshot) not in (
        ResolvedNifty50UniverseSnapshotV1,
        UniverseSnapshotNotFoundError,
        UniverseSnapshotStaleError,
        UniverseSnapshotAmbiguousError,
        UniverseSnapshotCorruptError,
    ):
        raise TypeError("invalid universe snapshot outcome")

    report, handoff = _admit_market_regime_participation_input(
        market_regime_facts_or_insufficiency
    )
    metadata, snapshot = _admit_resolved_snapshot_participation_input(resolved_snapshot)
    return report, handoff, metadata, snapshot


def _admit_market_regime_participation_input(
    market_regime_facts_or_insufficiency: object,
) -> tuple[
    MarketRegimeReportV1 | None,
    _MarketRegimeSectorHandoffV1 | None,
]:
    report: MarketRegimeReportV1 | None = None
    handoff: _MarketRegimeSectorHandoffV1 | None = None
    if type(market_regime_facts_or_insufficiency) is VerifiedMarketRegimeFactsV1:
        produced = _reduce_observed_market_regime_with_sector_handoff_v1(
            market_regime_facts_or_insufficiency
        )
        if (
            type(produced) is not tuple
            or len(produced) != 2
            or type(produced[0]) is not MarketRegimeReportV1
            or type(produced[1]) is not _MarketRegimeSectorHandoffV1
        ):
            raise ValueError("market regime reduction is inconsistent")
        report, handoff = produced
        try:
            report.__post_init__()
            handoff.__post_init__()
        except (TypeError, ValueError):
            raise ValueError("market regime reduction is inconsistent") from None
        if not _upstream_binding_matches(report, handoff):
            raise ValueError("market regime reduction is inconsistent")
    elif type(market_regime_facts_or_insufficiency) is MarketRegimeInsufficiencyV1:
        market_regime_facts_or_insufficiency.__post_init__()
    return report, handoff


def _admit_resolved_snapshot_participation_input(
    resolved_snapshot: object,
) -> tuple[
    UniverseSnapshotMetadataV1 | None,
    Nifty50UniverseSnapshotV1 | None,
]:
    metadata: UniverseSnapshotMetadataV1 | None = None
    snapshot: Nifty50UniverseSnapshotV1 | None = None
    if type(resolved_snapshot) is ResolvedNifty50UniverseSnapshotV1:
        metadata = resolved_snapshot.metadata
        snapshot = resolved_snapshot.snapshot
        if (
            type(metadata) is not UniverseSnapshotMetadataV1
            or type(snapshot) is not Nifty50UniverseSnapshotV1
        ):
            raise ValueError("resolved universe snapshot is inconsistent")
        try:
            metadata.__post_init__()
            snapshot.__post_init__()
        except (TypeError, ValueError):
            raise ValueError("resolved universe snapshot is inconsistent") from None
        snapshot_bytes = snapshot.canonical_json_bytes()
        if (
            metadata.snapshot_sha256 != hashlib.sha256(snapshot_bytes).hexdigest()
            or metadata.byte_count != len(snapshot_bytes)
            or _metadata_binding(metadata) != _snapshot_binding(snapshot)
        ):
            raise ValueError("resolved universe snapshot is inconsistent")
    return metadata, snapshot


def _snapshot_has_identity_bearing_sector_label(
    snapshot: Nifty50UniverseSnapshotV1,
) -> bool:
    constituent_isins = tuple(
        constituent.isin.upper() for constituent in snapshot.constituents
    )
    constituent_symbols = frozenset(
        constituent.symbol.upper() for constituent in snapshot.constituents
    )
    for constituent in snapshot.constituents:
        label = constituent.sector.upper()
        if any(isin in label for isin in constituent_isins):
            return True
        if not constituent_symbols.isdisjoint(re.findall(r"[A-Z0-9.&_-]+", label)):
            return True
    return False


def _sector_participation_reasons(
    report: MarketRegimeReportV1 | None,
    handoff: _MarketRegimeSectorHandoffV1 | None,
    resolved_snapshot: object,
    snapshot: Nifty50UniverseSnapshotV1 | None,
) -> tuple[list[SectorParticipationReasonV1], dict[str, str] | None]:
    reasons: list[SectorParticipationReasonV1] = []
    if report is None:
        reasons.append(SectorParticipationReasonV1.MARKET_REGIME_UNAVAILABLE)

    snapshot_reason = _snapshot_outcome_reason(resolved_snapshot)
    if snapshot_reason is not None:
        reasons.append(snapshot_reason)

    if snapshot is not None and _snapshot_has_identity_bearing_sector_label(snapshot):
        reasons.append(SectorParticipationReasonV1.SECTOR_CLASSIFICATION_CORRUPT)

    if report is not None and snapshot is not None:
        decision_date = date.fromisoformat(report.decision_session)
        cutoff = _utc_instant(report.evidence_cutoff)
        if not snapshot.effective_from <= decision_date <= snapshot.effective_to:
            reasons.append(SectorParticipationReasonV1.SECTOR_EFFECTIVE_SCOPE_MISMATCH)
        if (
            snapshot.membership_published_at > cutoff
            or snapshot.membership_retrieved_at > cutoff
            or snapshot.sector_published_at > cutoff
            or snapshot.sector_retrieved_at > cutoff
        ):
            reasons.append(SectorParticipationReasonV1.EVIDENCE_CUTOFF_MISMATCH)

    directions: dict[str, str] | None = None
    if handoff is not None and snapshot is not None:
        directions = {member.isin: member.direction for member in handoff.members}
        constituent_isins = {member.isin for member in snapshot.constituents}
        if set(directions) != constituent_isins or len(directions) != 50:
            reasons.append(SectorParticipationReasonV1.MEMBER_IDENTITY_MISMATCH)
    return reasons, directions


def _observed_sector_participation_report(
    report: MarketRegimeReportV1,
    handoff: _MarketRegimeSectorHandoffV1,
    metadata: UniverseSnapshotMetadataV1,
    snapshot: Nifty50UniverseSnapshotV1,
    directions: dict[str, str],
) -> SectorParticipationReportV1:
    counts: dict[str, list[int]] = {}
    for constituent in snapshot.constituents:
        row = counts.setdefault(constituent.sector, [0, 0, 0])
        direction = directions[constituent.isin]
        if direction == "ADVANCE":
            row[0] += 1
        elif direction == "DECLINE":
            row[1] += 1
        else:
            row[2] += 1
    sectors = tuple(
        SectorCountV1(
            label=label,
            member_count=sum(values),
            advances=values[0],
            declines=values[1],
            unchanged=values[2],
        )
        for label, values in sorted(counts.items())
    )

    identities = _sector_identities(report, handoff, metadata, snapshot)
    values: dict[str, object] = {
        "contract_version": "nifty50-sector-participation@v1",
        "calculation_version": "nifty50-sector-participation-counter@v1",
        "request_identity_sha256": report.request_identity_sha256,
        "market_regime_report_identity_sha256": report.report_identity_sha256,
        "input_identity_sha256": identities[0],
        "source_policy_identity_sha256": identities[1],
        "validation_policy_identity_sha256": identities[2],
        "privacy_policy_identity_sha256": identities[3],
        "licence_policy_identity_sha256": identities[4],
        "policy_identity_sha256": identities[5],
        "code_identity_sha256": identities[6],
        "decision_session": report.decision_session,
        "comparison_session": report.comparison_session,
        "decision_market_close": report.decision_market_close,
        "evidence_cutoff": report.evidence_cutoff,
        "required_member_count": 50,
        "evidence_state": "OBSERVED",
        "sectors": sectors,
        "primary_reason": None,
        "additional_reasons": (),
    }
    identity = hashlib.sha256(canonical_json_lf(values)).hexdigest()
    return SectorParticipationReportV1(
        contract_version="nifty50-sector-participation@v1",
        calculation_version="nifty50-sector-participation-counter@v1",
        request_identity_sha256=report.request_identity_sha256,
        market_regime_report_identity_sha256=report.report_identity_sha256,
        input_identity_sha256=identities[0],
        source_policy_identity_sha256=identities[1],
        validation_policy_identity_sha256=identities[2],
        privacy_policy_identity_sha256=identities[3],
        licence_policy_identity_sha256=identities[4],
        policy_identity_sha256=identities[5],
        code_identity_sha256=identities[6],
        decision_session=report.decision_session,
        comparison_session=report.comparison_session,
        decision_market_close=report.decision_market_close,
        evidence_cutoff=report.evidence_cutoff,
        required_member_count=50,
        evidence_state="OBSERVED",
        sectors=sectors,
        primary_reason=None,
        additional_reasons=(),
        report_identity_sha256=identity,
    )


def _snapshot_outcome_reason(
    outcome: object,
) -> SectorParticipationReasonV1 | None:
    if outcome is None or type(outcome) is UniverseSnapshotNotFoundError:
        return SectorParticipationReasonV1.SECTOR_CLASSIFICATION_MISSING
    if type(outcome) is UniverseSnapshotStaleError:
        return SectorParticipationReasonV1.SECTOR_CLASSIFICATION_STALE
    if type(outcome) is UniverseSnapshotAmbiguousError:
        return SectorParticipationReasonV1.SECTOR_CLASSIFICATION_AMBIGUOUS
    if type(outcome) is UniverseSnapshotCorruptError:
        return SectorParticipationReasonV1.SECTOR_CLASSIFICATION_CORRUPT
    return None


def _upstream_binding_matches(
    report: MarketRegimeReportV1,
    handoff: _MarketRegimeSectorHandoffV1,
) -> bool:
    return (
        handoff.market_regime_contract_version == report.contract_version
        and handoff.market_regime_report_identity_sha256
        == report.report_identity_sha256
        and handoff.market_regime_input_identity_sha256 == report.input_identity_sha256
        and handoff.source_policy_identity_sha256
        == report.source_policy_identity_sha256
        and handoff.validation_policy_identity_sha256
        == report.validation_policy_identity_sha256
        and handoff.policy_identity_sha256 == report.policy_identity_sha256
        and handoff.code_identity_sha256 == report.code_identity_sha256
        and handoff.comparison_session == report.comparison_session
        and handoff.decision_session == report.decision_session
        and handoff.decision_market_close == report.decision_market_close
        and handoff.evidence_cutoff == report.evidence_cutoff
        and sum(member.direction == "ADVANCE" for member in handoff.members)
        == report.advances
        and sum(member.direction == "DECLINE" for member in handoff.members)
        == report.declines
        and sum(member.direction == "UNCHANGED" for member in handoff.members)
        == report.unchanged
    )


def _metadata_binding(metadata: UniverseSnapshotMetadataV1) -> tuple[object, ...]:
    return (
        metadata.schema_version,
        metadata.universe_id,
        metadata.effective_from,
        metadata.effective_to,
        metadata.membership_source,
        metadata.membership_release,
        metadata.membership_published_at,
        metadata.membership_retrieved_at,
        metadata.sector_source,
        metadata.sector_release,
        metadata.sector_published_at,
        metadata.sector_retrieved_at,
    )


def _snapshot_binding(snapshot: Nifty50UniverseSnapshotV1) -> tuple[object, ...]:
    return (
        snapshot.schema_version,
        snapshot.universe_id,
        snapshot.effective_from,
        snapshot.effective_to,
        snapshot.membership_source,
        snapshot.membership_release,
        snapshot.membership_published_at,
        snapshot.membership_retrieved_at,
        snapshot.sector_source,
        snapshot.sector_release,
        snapshot.sector_published_at,
        snapshot.sector_retrieved_at,
    )


def _utc_instant(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(UTC)


def _identity(value: object) -> str:
    return hashlib.sha256(canonical_json_lf(value)).hexdigest()


def _sector_identities(
    report: MarketRegimeReportV1,
    handoff: _MarketRegimeSectorHandoffV1,
    metadata: UniverseSnapshotMetadataV1,
    snapshot: Nifty50UniverseSnapshotV1,
) -> tuple[str, str, str, str, str, str, str]:
    input_identity = _identity(
        {
            "contract_version": "nifty50-sector-participation-input@v1",
            "market_regime_input_identity_sha256": report.input_identity_sha256,
            "market_regime_report_identity_sha256": report.report_identity_sha256,
            "market_regime_sector_handoff_identity_sha256": (
                handoff.handoff_identity_sha256
            ),
            "universe_snapshot_sha256": metadata.snapshot_sha256,
        }
    )
    source_identity = _identity(
        {
            "contract_version": "nifty50-sector-participation-resolved-sources@v1",
            "market_regime_source_policy_identity_sha256": (
                report.source_policy_identity_sha256
            ),
            "membership_release": snapshot.membership_release,
            "membership_source": snapshot.membership_source,
            "sector_release": snapshot.sector_release,
            "sector_source": snapshot.sector_source,
        }
    )
    validation_identity = _identity(
        {
            "contract_version": "nifty50-sector-participation-validation@v1",
            "market_regime_validation_policy_identity_sha256": (
                report.validation_policy_identity_sha256
            ),
            "universe_snapshot_schema_version": snapshot.schema_version,
        }
    )
    privacy_identity = _identity(
        {
            "contract_version": "nifty50-sector-participation-private-output@v1",
            "member_identifiers_in_report": False,
        }
    )
    licence_identity = _identity(
        {
            "classification_authority_claim": "NONE",
            "contract_version": "nifty50-sector-participation-opaque-labels@v1",
            "licence_claim": "NONE",
        }
    )
    policy_identity = _identity(
        {
            "licence_policy_identity_sha256": licence_identity,
            "privacy_policy_identity_sha256": privacy_identity,
            "source_policy_identity_sha256": source_identity,
            "validation_policy_identity_sha256": validation_identity,
        }
    )
    code_identity = _identity(
        {
            "calculation_version": "nifty50-sector-participation-counter@v1",
            "market_regime_code_identity_sha256": report.code_identity_sha256,
        }
    )
    return (
        input_identity,
        source_identity,
        validation_identity,
        privacy_identity,
        licence_identity,
        policy_identity,
        code_identity,
    )
