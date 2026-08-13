"""Provider-free application service for the strict retained census."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

from .census import OpportunityCensusReportV1, build_strict_retained_census_v1


@dataclass(frozen=True, slots=True)
class RetainedCensusRequestV1:
    seal_path: Path
    code_sha: str
    configuration_sha256: str


class RetainedCensusServiceV1:
    """Validate an explicit immutable seal and build a zero-provider report."""

    def run(self, request: RetainedCensusRequestV1) -> OpportunityCensusReportV1:
        try:
            parsed: object = json.loads(request.seal_path.read_bytes())
            if type(parsed) is not dict:
                raise ValueError
            value = cast(dict[str, object], parsed)
            if (
                value.get("provider_attempt_count") != 0
                or value.get("stock_count") != 50
                or value.get("partition_count") != 100
            ):
                raise ValueError
            identity = value.get("dataset_identity_sha256")
            raw_selections = value.get("selections")
            if (
                type(identity) is not str
                or len(identity) != 64
                or type(raw_selections) is not list
            ):
                raise ValueError
            selections = cast(list[object], raw_selections)
            keys: set[tuple[str, str]] = set()
            for raw in selections:
                if type(raw) is not dict:
                    raise ValueError
                item = cast(dict[str, object], raw)
                isin, month = item.get("isin"), item.get("month")
                if type(isin) is not str or type(month) is not str:
                    raise ValueError
                keys.add((isin, month))
            if len(selections) != 100 or len(keys) != 100:
                raise ValueError
            july = (
                1,
                2,
                3,
                6,
                7,
                8,
                9,
                10,
                13,
                14,
                15,
                16,
                17,
                20,
                21,
                22,
                23,
                24,
                27,
                28,
                29,
                30,
                31,
            )
            august = (3, 4, 5, 6, 7, 10, 11, 12)
            sessions = tuple(date(2026, 7, d) for d in july) + tuple(
                date(2026, 8, d) for d in august
            )
            return build_strict_retained_census_v1(
                stock_count=50,
                decision_sessions=sessions,
                universe_known_at=datetime(2026, 8, 12, 8, 56, 38, 181171, tzinfo=UTC),
                corporate_action_evidence_available=False,
                evidence_seal_sha256=identity,
                code_sha=request.code_sha,
                configuration_sha256=request.configuration_sha256,
            )
        except Exception:
            raise ValueError("retained census evidence unavailable") from None
