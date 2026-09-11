from __future__ import annotations

import sys
from datetime import timedelta
from importlib import util
from pathlib import Path

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.research_packet import (
    current_supplied_cohort_v4 as packet,
)


def _load(relative, name):
    path = Path(__file__).parents[1] / relative
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_retained_v4_packet_preserves_event_failure_and_exact_retry(tmp_path):
    fixture = _load(
        "sector_analysis/test_bharatstock_industry_v4.py", "packet_v4_industry_fixture"
    )

    def inspect(_scenario, market_request, context, _classification, industry):
        request = packet.CurrentSuppliedCohortResearchPacketRequestV4(
            decision_cutoff=market_request.decision_cutoff,
            cohort_selected_at=market_request.cohort_selected_at,
            members=market_request.members,
            market_context_identity_sha256=context.context_identity_sha256,
        )
        event_test = _load(
            "market_data/test_current_event_notice.py", "packet_v4_event_fixture"
        )
        event_failure = event_test._parse(event_test._api(), b"")
        root = tmp_path / "packet"
        root.mkdir(mode=0o700)
        acquired = StorageRootLease.try_acquire(root)
        assert acquired.lease is not None

        class Clock:
            def __init__(self):
                self.values = [request.decision_cutoff - timedelta(seconds=30)] + [
                    request.decision_cutoff
                ] * 100

            def now(self):
                return self.values.pop(0)

        def build():
            clock = Clock()
            return packet.build_and_retain_current_supplied_cohort_research_packet_v4(
                request,
                context,
                industry,
                event_failure,
                packet.FileCurrentResearchPacketArchiveV4(root, clock=clock),
                acquired.lease,
                trusted_clock=clock,
            )

        try:
            first = build()
            assert type(first) is packet.RetainedCurrentSuppliedCohortResearchPacketV4
            assert first.packet.evidence_state == "INSUFFICIENT_EVIDENCE"
            assert (
                first.packet.ai_projection.consumer_disposition
                == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
            )
            second = build()
            assert second.canonical_json_bytes() == first.canonical_json_bytes()
            assert (root / ".current-research-packet-v4").is_dir()
        finally:
            acquired.lease.close()

    fixture._with_industry(tmp_path, inspect)
