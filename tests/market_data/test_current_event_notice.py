"""RED contract tests for owner-private current NSE event notices V1."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_SOURCE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements?tabIndex=equity"
_HEADER = (
    "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,"
    "DISSEMINATION,DIFFERENCE,ATTACHMENT"
)
_FILENAME = "CF-AN-equities-23-Aug-2026.csv"
_KNOWN_AT = datetime(2026, 8, 23, 10, tzinfo=UTC)


def _expected_schema_identity() -> str:
    """Return the independently declared public schema-binding identity."""
    binding = {
        "contract_version": "current-supplied-cohort-event-notice@v1",
        "header": [
            "SYMBOL",
            "COMPANY NAME",
            "SUBJECT",
            "DETAILS",
            "BROADCAST DATE/TIME",
            "RECEIPT",
            "DISSEMINATION",
            "DIFFERENCE",
            "ATTACHMENT",
        ],
        "source": {
            "url": _SOURCE_URL,
            "segment": "Equity",
            "window": "1D",
            "filename_grammar": r"CF-AN-equities-(\d{2}-[A-Za-z]{3}-\d{4})\.csv\Z",
            "licence_policy_identity": "nse-manual-download-owner-private-v1",
            "row_date_window": {
                "current_source_filename_date": True,
                "prior_calendar_days": 1,
            },
        },
        "csv": {
            "utf8_bom_required": True,
            "utf8_decode_after_bom": True,
            "string_io_newline": "",
            "reader_strict": True,
            "decoded_header_exact": [
                "SYMBOL",
                "COMPANY NAME",
                "SUBJECT",
                "DETAILS",
                "BROADCAST DATE/TIME",
                "RECEIPT",
                "DISSEMINATION",
                "DIFFERENCE",
                "ATTACHMENT",
            ],
        },
        "bounds": {
            "artifact_bytes": [1, 4_194_304],
            "rows": [1, 10_000],
            "fields": 9,
            "field_code_points": [1, 32_768],
            "archive_snapshot_bytes": 33_554_432,
            "archive_receipt_bytes": 16_384,
            "archive_marker_bytes": 4_096,
        },
        "grammars": {
            "symbol": r"[A-Z0-9](?:[A-Z0-9.&_-]{0,30}[A-Z0-9])?\Z",
            "isin": r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z",
            "attachment_prefix": "https://nsearchives.nseindia.com/corporate/",
            "workflow_time": r"\d{2}-[A-Z][a-z]{2}-\d{4} \d{2}:\d{2}:\d{2}\Z",
            "receipt_time": r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\Z",
            "difference": r"\d{2}:\d{2}:\d{2}\Z",
            "english_months": (
                "Jan",
                "Feb",
                "Mar",
                "Apr",
                "May",
                "Jun",
                "Jul",
                "Aug",
                "Sep",
                "Oct",
                "Nov",
                "Dec",
            ),
            "month_mapping": {
                "Jan": 1,
                "Feb": 2,
                "Mar": 3,
                "Apr": 4,
                "May": 5,
                "Jun": 6,
                "Jul": 7,
                "Aug": 8,
                "Sep": 9,
                "Oct": 10,
                "Nov": 11,
                "Dec": 12,
            },
            "calendar_component_validation": {
                "workflow": "Gregorian-date-hour-minute-second",
                "receipt": "Gregorian-date-hour-minute-second",
            },
            "difference_hour_range": [0, 99],
            "difference_minute_range": [0, 59],
            "difference_second_range": [0, 59],
        },
        "text_policy": {
            "unicode": "no-Cc-Cf-Zl-Zp",
            "formula_prefixes": ["=", "+", "-", "@"],
            "canonicalization": "json-sort-keys-utf8-newline",
        },
        "correction": {
            "normalization": "NFKC-casefold-maximal-ascii-alnum",
            "subject_tokens": [
                "cancellation",
                "clarification",
                "correction",
                "supersession",
                "withdrawal",
            ],
            "details_phrases": [
                "correction to our earlier announcement",
                "clarification to our earlier announcement",
                "withdrawal of our earlier announcement",
                "cancellation of our earlier announcement",
                "supersedes our earlier announcement",
                "correction to our previous disclosure",
                "clarification to our previous disclosure",
            ],
        },
        "archive": {
            "protocol": "current-event-notice-archive@v1",
            "receipt_version": "retained-current-event-notice-receipt@v1",
            "marker_version": "retained-current-event-notice-complete@v1",
            "publication": "create-only-0600-no-follow-stable-binding-fsync",
            "known_at_ownership": "archive-trusted-utc-at-first-publication",
            "current_request_admission": (
                "original-known-at-and-current-trusted-utc-must-map-to-"
                "source-filename-ist-date"
            ),
            "current_request_date_failures": {
                "before": "EVENT_SOURCE_DATE_FUTURE",
                "after": "EVENT_SOURCE_DATE_STALE",
            },
        },
    }
    canonical = (
        json.dumps(
            binding,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    return hashlib.sha256(canonical).hexdigest()


def _api() -> Any:
    return importlib.import_module(
        "swing_trading_ai_assistant.market_data.current_event_notice"
    )


def _isin(index: int) -> str:
    """Return a deterministic syntactically and checksum-valid ISIN."""
    stem = f"INE{index:08d}"
    converted = "".join(
        str(ord(char) - 55) if char.isalpha() else char for char in stem
    )
    for check in range(10):
        digits = converted + str(check)
        total = sum(
            int(digit) * (2 if position % 2 else 1)
            for position, digit in enumerate(reversed(digits))
        )
        total = sum(
            number if number < 10 else number - 9
            for number in [
                int(digit) * (2 if position % 2 else 1)
                for position, digit in enumerate(reversed(digits))
            ]
        )
        if total % 10 == 0:
            return stem + str(check)
    raise AssertionError("unreachable ISO 6166 check digit")


def _artifact(rows: list[tuple[str, ...]] | None = None) -> bytes:
    values = rows or [
        (
            "ALPHA",
            "Alpha Limited",
            '"Board meeting, update"',
            '"Quarterly update, no event date"',
            "23-Aug-2026 14:00:00",
            "2026-08-23 13:59:00",
            "23-Aug-2026 14:00:01",
            "00:00:01",
            "https://nsearchives.nseindia.com/corporate/alpha.pdf",
        ),
        (
            "OUTSIDE",
            "Outside Limited",
            "Unrelated disclosure",
            "Private full-market source row",
            "23-Aug-2026 14:00:00",
            "2026-08-23 13:59:00",
            "23-Aug-2026 14:00:01",
            "00:00:01",
            "https://nsearchives.nseindia.com/corporate/outside.pdf",
        ),
    ]
    return (
        "\ufeff" + "\n".join((_HEADER, *(",".join(row) for row in values))) + "\n"
    ).encode()


def _input(api: Any, artifact: bytes, **changes: object) -> Any:
    values: dict[str, object] = {
        "schema_identity_sha256": api.EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        "source_url": _SOURCE_URL,
        "source_segment": "Equity",
        "source_window": "1D",
        "source_filename": _FILENAME,
        "artifact_identity_sha256": hashlib.sha256(artifact).hexdigest(),
        "licence_policy_identity": "nse-manual-download-owner-private-v1",
    }
    values.update(changes)
    return api.CurrentEventNoticeInputV1(**values)


def _members(api: Any, size: int = 2, **changes: object) -> tuple[Any, ...]:
    members: list[object] = []
    for index in range(size):
        values: dict[str, object] = {
            "isin": _isin(index),
            "exchange": "NSE",
            "listed_equity_segment": "EQUITY",
            "symbol": ("ALPHA", "BETA")[index] if index < 2 else f"X{index}",
            "effective_from": date(2020, 1, 1),
            "effective_through": date(2030, 1, 1),
            "provider_mapping_revision": "canonical-mapping-v1",
        }
        values.update(changes)
        members.append(api.CurrentEventCohortMemberV1(**values))
    return tuple(members)


def _parse(api: Any, artifact: bytes, **changes: object) -> Any:
    return api.parse_current_event_notice_artifact_v1(
        _input(api, artifact, **changes), artifact
    )


def _failure(value: Any, state: str, reason: str) -> None:
    assert value.evidence_state == state
    assert value.reasons == (reason,)
    public = repr(value)
    for secret in ("ALPHA", _isin(0), "Private full-market", str(Path.cwd())):
        assert secret not in public


def _lease(tmp_path: Path) -> StorageRootLease:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    return acquired.lease


def _project(api: Any, artifact: bytes | None = None, size: int = 2) -> Any:
    raw = _artifact() if artifact is None else artifact
    parsed = _parse(api, raw)
    assert parsed.evidence_state == "PARSED"
    snapshot = api.project_current_supplied_cohort_event_notices_v1(
        parsed, _members(api, size)
    )
    assert snapshot.evidence_state == "PROJECTED"
    return snapshot


def _bse_members(api: Any) -> tuple[Any, ...]:
    return _members(api, exchange="BSE")


def _duplicate_members(api: Any) -> tuple[Any, ...]:
    return (_members(api, 1)[0], _members(api, 1)[0])


def _expired_members(api: Any) -> tuple[Any, ...]:
    return _members(api, effective_through=date(2026, 8, 22))


def test_exact_input_schema_source_licence_and_redacted_representations() -> None:
    api = _api()
    raw = _artifact()
    parsed = _parse(api, raw)
    assert parsed.schema_identity_sha256 == api.EVENT_NOTICE_SCHEMA_IDENTITY_SHA256
    assert _expected_schema_identity() == api.EVENT_NOTICE_SCHEMA_IDENTITY_SHA256
    _failure(
        _parse(api, raw, licence_policy_identity="caller-chosen"),
        "UNSUPPORTED_CAPABILITY",
        "EVENT_SOURCE_UNAUTHORIZED",
    )
    with pytest.raises(TypeError, match="private event row constructor unavailable"):
        api._PrivateEventNoticeRow()


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (_artifact()[3:], "EVENT_ARTIFACT_MALFORMED"),
        (
            _artifact().replace(_HEADER.encode(), b"SYMBOL,WRONG"),
            "EVENT_HEADER_MISMATCH",
        ),
        (
            _artifact().replace(b"Alpha Limited", b"=FORMULA"),
            "EVENT_ARTIFACT_MALFORMED",
        ),
        (
            _artifact().replace(b"Alpha Limited", b"Alpha\x00Limited"),
            "EVENT_ARTIFACT_MALFORMED",
        ),
        (b"\xef\xbb\xbf" + _artifact()[3:] + b"trailing", "EVENT_ARTIFACT_MALFORMED"),
    ],
)
def test_csv_bom_header_quoting_and_hostile_cells_fail_closed(
    raw: bytes, reason: str
) -> None:
    api = _api()
    _failure(_parse(api, raw), "MALFORMED_EVIDENCE", reason)


def test_csv_final_record_without_newline_is_admitted_but_truncated_csv_is_rejected() -> (
    None
):
    api = _api()
    without_final_newline = _artifact()[:-1]

    parsed = _parse(api, without_final_newline)

    assert parsed.evidence_state == "PARSED"
    _failure(
        _parse(api, without_final_newline + b'\n"unterminated'),
        "MALFORMED_EVIDENCE",
        "EVENT_ARTIFACT_MALFORMED",
    )


def test_parser_preserves_literal_times_and_explicit_unavailable_publisher_fields() -> (
    None
):
    api = _api()
    parsed = _parse(api, _artifact())
    row = parsed.private_rows[0]
    assert row.broadcast_at == "23-Aug-2026 14:00:00"
    assert row.receipt_at == "2026-08-23 13:59:00"
    assert row.dissemination_at == "23-Aug-2026 14:00:01"
    assert row.publisher_timezone is row.event_at is row.publisher_event_id is None
    assert row.publisher_revision_id is row.correction_of is None


def test_exact_cohort_projection_excludes_unrelated_rows_and_emits_no_match() -> None:
    api = _api()
    snapshot = _project(api)
    assert snapshot.cohort_size == 2
    alpha, beta = snapshot.members
    assert alpha.member.symbol == "ALPHA"
    assert len(alpha.notices) == 1
    assert beta.outcome == "NO_MATCHING_NOTICE_IN_SNAPSHOT"
    encoded = snapshot.canonical_json_bytes().decode()
    assert "OUTSIDE" not in encoded
    assert "Private full-market" not in encoded
    assert "NO_MATCHING_NOTICE_IN_SNAPSHOT" in encoded


@pytest.mark.parametrize("size", (0, 51))
def test_cohort_size_is_closed_at_one_to_fifty(size: int) -> None:
    api = _api()
    parsed = _parse(api, _artifact())
    with pytest.raises(ValueError, match="event cohort invalid"):
        api.project_current_supplied_cohort_event_notices_v1(
            parsed, _members(api, size)
        )


@pytest.mark.parametrize(
    ("members", "state", "reason"),
    [
        (
            _bse_members,
            "UNSUPPORTED_CAPABILITY",
            "EVENT_EXCHANGE_UNSUPPORTED",
        ),
        (
            _duplicate_members,
            "MALFORMED_EVIDENCE",
            "EVENT_SYMBOL_AMBIGUOUS",
        ),
        (
            _expired_members,
            "MALFORMED_EVIDENCE",
            "EVENT_COHORT_INVALID",
        ),
    ],
)
def test_cohort_binding_failures_are_typed(
    members: Callable[[Any], tuple[Any, ...]], state: str, reason: str
) -> None:
    api = _api()
    result = api.project_current_supplied_cohort_event_notices_v1(
        _parse(api, _artifact()), members(api)
    )
    _failure(result, state, reason)


@pytest.mark.parametrize(
    ("rows", "state", "reason"),
    [
        (
            [
                (
                    "ALPHA",
                    "Alpha",
                    "S",
                    "D",
                    "24-Aug-2026 00:00:00",
                    "2026-08-24 00:00:00",
                    "24-Aug-2026 00:00:00",
                    "00:00:00",
                    "https://nsearchives.nseindia.com/corporate/a.pdf",
                ),
            ],
            "INSUFFICIENT_EVIDENCE",
            "EVENT_SOURCE_DATE_FUTURE",
        ),
        (
            [
                (
                    "ALPHA",
                    "Alpha",
                    "S",
                    "D",
                    "21-Aug-2026 00:00:00",
                    "2026-08-21 00:00:00",
                    "21-Aug-2026 00:00:00",
                    "00:00:00",
                    "https://nsearchives.nseindia.com/corporate/a.pdf",
                ),
            ],
            "INSUFFICIENT_EVIDENCE",
            "EVENT_SOURCE_DATE_STALE",
        ),
        (
            [
                (
                    "ALPHA",
                    "Alpha",
                    "Amendment to AOA/MOA",
                    "D",
                    "23-Aug-2026 00:00:00",
                    "2026-08-23 00:00:00",
                    "23-Aug-2026 00:00:00",
                    "00:00:00",
                    "https://nsearchives.nseindia.com/corporate/a.pdf",
                ),
            ],
            "PARSED",
            "",
        ),
        (
            [
                (
                    "ALPHA",
                    "Alpha",
                    "S",
                    "correction to our earlier announcement",
                    "23-Aug-2026 00:00:00",
                    "2026-08-23 00:00:00",
                    "23-Aug-2026 00:00:00",
                    "00:00:00",
                    "https://nsearchives.nseindia.com/corporate/a.pdf",
                ),
            ],
            "PROJECT_FAILURE",
            "CORRECTION_LINEAGE_UNAVAILABLE",
        ),
    ],
)
def test_date_and_closed_correction_gate_boundaries(
    rows: list[tuple[str, ...]], state: str, reason: str
) -> None:
    api = _api()
    value = _parse(api, _artifact(rows))
    if state == "PARSED":
        assert value.evidence_state == state
    elif state == "PROJECT_FAILURE":
        assert value.evidence_state == "PARSED"
        _failure(
            api.project_current_supplied_cohort_event_notices_v1(value, _members(api)),
            "INSUFFICIENT_EVIDENCE",
            reason,
        )
    else:
        _failure(value, state, reason)


def test_duplicate_and_conflicting_admitted_rows_fail_whole_artifact() -> None:
    api = _api()
    row = (
        "ALPHA",
        "Alpha",
        "S",
        "D",
        "23-Aug-2026 00:00:00",
        "2026-08-23 00:00:00",
        "23-Aug-2026 00:00:00",
        "00:00:00",
        "https://nsearchives.nseindia.com/corporate/a.pdf",
    )
    _failure(
        api.project_current_supplied_cohort_event_notices_v1(
            _parse(api, _artifact([row, row])), _members(api)
        ),
        "CONFLICTED_EVIDENCE",
        "EVENT_DUPLICATE",
    )
    changed = (*row[:3], "other", *row[4:])
    _failure(
        api.project_current_supplied_cohort_event_notices_v1(
            _parse(api, _artifact([row, changed])), _members(api)
        ),
        "CONFLICTED_EVIDENCE",
        "EVENT_CONFLICTED",
    )


def _retain(
    api: Any, root: Path, snapshot: Any, lease: StorageRootLease, raw: bytes
) -> Any:
    return api.FileCurrentEventNoticeArchiveV1(root).archive_exact(
        _input(api, raw), raw, snapshot, lease
    )


def test_retention_binds_separate_identities_and_archive_owned_known_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    snapshot = _project(api)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, snapshot, lease, _artifact())
    assert retained.evidence_state == "RETAINED"
    assert retained.known_at == _KNOWN_AT
    identities = {
        retained.artifact_identity_sha256,
        retained.snapshot_identity_sha256,
        retained.archive_identity_sha256,
        retained.receipt_identity_sha256,
        retained.runtime_code_identity_sha256,
        retained.retained_identity_sha256,
        retained.members[0].notices[0].observation_identity_sha256,
        retained.members[0].notices[0].deduplication_identity_sha256,
    }
    assert len(identities) == 8
    assert "ALPHA" not in repr(retained)


def test_first_publication_samples_known_at_after_durable_content_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    raw = _artifact()
    snapshot = _project(api, raw)
    archive_identity = api._archive_identity(snapshot)
    raw_name, snapshot_name, receipt_name, marker_name = api._archive_names(
        snapshot, archive_identity
    )
    events: list[str] = []
    real_publish = api._publish_object
    real_verify = api._verify_archive_binding
    real_require_source_date = api._require_source_ist_date

    def publish(parent: int, name: str, value: bytes, maximum_size: int) -> bool:
        published = real_publish(parent, name, value, maximum_size)
        events.append(f"published:{name}")
        return published

    def verify(
        operation: object,
        root: int,
        directory: int,
        artifact_name: str,
        artifact: bytes,
        projection_name: str,
        projection: bytes,
    ) -> None:
        real_verify(
            operation,
            root,
            directory,
            artifact_name,
            artifact,
            projection_name,
            projection,
        )
        events.append("content-bound")

    def trusted_now() -> datetime:
        events.append("known-at-sampled")
        return _KNOWN_AT

    def require_source_date(value: Any, observed_at: datetime) -> None:
        real_require_source_date(value, observed_at)
        events.append("known-at-fresh")

    monkeypatch.setattr(api, "_publish_object", publish)
    monkeypatch.setattr(api, "_verify_archive_binding", verify)
    monkeypatch.setattr(api, "_trusted_utc_now", trusted_now)
    monkeypatch.setattr(api, "_require_source_ist_date", require_source_date)

    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, snapshot, lease, raw)

    assert retained.known_at == _KNOWN_AT
    assert events.count("known-at-sampled") == 1
    assert max(
        events.index(f"published:{raw_name}"),
        events.index(f"published:{snapshot_name}"),
        events.index("content-bound"),
    ) < events.index("known-at-sampled")
    assert events.index("known-at-sampled") < events.index("known-at-fresh")
    assert events.index("known-at-fresh") < min(
        events.index(f"published:{receipt_name}"),
        events.index(f"published:{marker_name}"),
    )


def test_retention_rejects_knowledge_time_outside_filename_ist_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(
        api, "_trusted_utc_now", lambda: datetime(2026, 8, 24, 1, tzinfo=UTC)
    )
    with _lease(tmp_path) as lease:
        _failure(
            _retain(api, tmp_path, _project(api), lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_SOURCE_DATE_STALE",
        )


def test_retry_uses_original_known_at_and_changed_artifact_is_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    first = _project(api)
    changed = _artifact().replace(b"Quarterly update", b"Different update")
    second = _project(api, changed)
    with _lease(tmp_path) as lease:
        one = _retain(api, tmp_path, first, lease, _artifact())
        monkeypatch.setattr(
            api, "_trusted_utc_now", lambda: datetime(2026, 8, 23, 12, tzinfo=UTC)
        )
        retry = _retain(api, tmp_path, first, lease, _artifact())
        two = _retain(api, tmp_path, second, lease, changed)
    assert retry.known_at == one.known_at
    assert two.artifact_identity_sha256 != one.artifact_identity_sha256
    assert two.archive_identity_sha256 != one.archive_identity_sha256


@pytest.mark.parametrize(
    ("trusted_now", "reason"),
    [
        (datetime(2026, 8, 23, 18, 30, tzinfo=UTC), "EVENT_SOURCE_DATE_STALE"),
        (datetime(2026, 8, 22, 18, 29, tzinfo=UTC), "EVENT_SOURCE_DATE_FUTURE"),
    ],
)
def test_retry_requires_current_trusted_time_on_source_ist_date_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trusted_now: datetime,
    reason: str,
) -> None:
    api = _api()
    raw = _artifact()
    snapshot = _project(api, raw)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, snapshot, lease, raw)
        root = tmp_path / ".current-event-notice-v1"
        before = {path.name: path.read_bytes() for path in root.iterdir()}
        receipt = json.loads(before[f"{retained.archive_identity_sha256}.receipt.json"])

        monkeypatch.setattr(api, "_trusted_utc_now", lambda: trusted_now)
        retry = _retain(api, tmp_path, snapshot, lease, raw)

        _failure(retry, "INSUFFICIENT_EVIDENCE", reason)
        assert receipt["known_at"] == "2026-08-23T10:00:00.000000Z"
        assert receipt["receipt_identity_sha256"] == retained.receipt_identity_sha256
        assert receipt["retained_identity_sha256"] == retained.retained_identity_sha256
        assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_archive_corruption_and_runtime_identity_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    snapshot = _project(api)
    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, snapshot, lease, _artifact())
        root = tmp_path / ".current-event-notice-v1"
        (root / f"{retained.archive_identity_sha256}.receipt.json").write_text("{}")
        _failure(
            _retain(api, tmp_path, snapshot, lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_ARCHIVE_FAILED",
        )
    monkeypatch.setattr(api, "_EVENT_NOTICE_RUNTIME_IDENTITY", "0" * 64)
    with _lease(tmp_path) as lease:
        _failure(
            _retain(api, tmp_path, snapshot, lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_RUNTIME_IDENTITY_INVALID",
        )


def test_pure_parse_and_projection_do_not_touch_clock_or_network_or_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    monkeypatch.setattr(
        api, "_trusted_utc_now", lambda: (_ for _ in ()).throw(AssertionError("clock"))
    )
    parsed = _parse(api, _artifact())
    snapshot = api.project_current_supplied_cohort_event_notices_v1(
        parsed, _members(api)
    )
    assert snapshot.evidence_state == "PROJECTED"


def test_observed_official_shape_smoke_without_live_participation_claim() -> None:
    api = _api()
    raw = _artifact()
    parsed = _parse(api, raw)
    assert parsed.evidence_state == "PARSED"
    assert parsed.artifact_identity_sha256 == hashlib.sha256(raw).hexdigest()


def _forge_snapshot(api: Any, snapshot: Any, **changes: object) -> Any:
    values = {
        "evidence_state": snapshot.evidence_state,
        "schema_identity_sha256": snapshot.schema_identity_sha256,
        "artifact_identity_sha256": snapshot.artifact_identity_sha256,
        "source_filename": snapshot.source_filename,
        "source_url": snapshot.source_url,
        "source_segment": snapshot.source_segment,
        "source_window": snapshot.source_window,
        "licence_policy_identity": snapshot.licence_policy_identity,
        "cohort_size": snapshot.cohort_size,
        "members": snapshot.members,
        "snapshot_identity_sha256": snapshot.snapshot_identity_sha256,
    }
    values.update(changes)
    return api._snapshot(**values)


def test_archive_reprojects_snapshot_and_rejects_forged_member_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    snapshot = _project(api)
    alpha = snapshot.members[0]
    forged_notice = api.CurrentEventNoticeV1(
        alpha.member,
        "OUTSIDE",
        "Outside Limited",
        "Unrelated",
        "Private full-market source row",
        "23-Aug-2026 14:00:00",
        "2026-08-23 13:59:00",
        "23-Aug-2026 14:00:01",
        "00:00:01",
        "https://nsearchives.nseindia.com/corporate/outside.pdf",
        "0" * 64,
        "1" * 64,
    )
    forged_member = api.CurrentEventNoticeMemberResultV1(
        alpha.member, "NOTICES_ADMITTED", (*alpha.notices, forged_notice)
    )
    forged = _forge_snapshot(
        api, snapshot, members=(forged_member, snapshot.members[1])
    )
    with _lease(tmp_path) as lease:
        _failure(
            _retain(api, tmp_path, forged, lease, _artifact()),
            "MALFORMED_EVIDENCE",
            "EVENT_OUT_OF_COHORT",
        )


def test_archive_rejects_internally_inconsistent_receipt_marker_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    snapshot = _project(api)
    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, snapshot, lease, _artifact())
        root = tmp_path / ".current-event-notice-v1"
        receipt_name = f"{retained.archive_identity_sha256}.receipt.json"
        marker_name = f"{retained.archive_identity_sha256}.complete.json"
        receipt = json.loads((root / receipt_name).read_text())
        receipt["receipt_identity_sha256"] = "2" * 64
        receipt["retained_identity_sha256"] = "3" * 64
        (root / receipt_name).write_bytes(api._canonical(receipt))
        (root / marker_name).write_bytes(
            api._marker_bytes(
                retained.archive_identity_sha256,
                receipt["receipt_identity_sha256"],
                receipt["known_at"],
                receipt["retained_identity_sha256"],
            )
        )
        _failure(
            _retain(api, tmp_path, snapshot, lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_ARCHIVE_FAILED",
        )


def test_stale_archive_failure_never_publishes_completed_objects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(
        api, "_trusted_utc_now", lambda: datetime(2026, 8, 24, 1, tzinfo=UTC)
    )
    snapshot = _project(api)
    archive_identity = api._archive_identity(snapshot)
    raw_name, snapshot_name, receipt_name, marker_name = api._archive_names(
        snapshot, archive_identity
    )
    with _lease(tmp_path) as lease:
        _failure(
            _retain(api, tmp_path, snapshot, lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_SOURCE_DATE_STALE",
        )
    root = tmp_path / ".current-event-notice-v1"
    assert {path.name for path in root.iterdir()} == {raw_name, snapshot_name}
    assert not (root / receipt_name).exists()
    assert not (root / marker_name).exists()


@pytest.mark.parametrize(
    "outside_rows",
    [
        [
            (
                "OUTSIDE",
                "Outside",
                "Correction",
                "D",
                "23-Aug-2026 00:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/outside.pdf",
            )
        ],
        [
            (
                "OUTSIDE",
                "Outside",
                "S",
                "D",
                "23-Aug-2026 00:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/outside.pdf",
            ),
            (
                "OUTSIDE",
                "Outside",
                "S",
                "D",
                "23-Aug-2026 00:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/outside.pdf",
            ),
        ],
        [
            (
                "OUTSIDE",
                "Outside",
                "S",
                "D",
                "23-Aug-2026 00:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/outside.pdf",
            ),
            (
                "OUTSIDE",
                "Outside",
                "S",
                "changed",
                "23-Aug-2026 00:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/outside.pdf",
            ),
        ],
    ],
)
def test_unrelated_full_market_conflicts_remain_private(
    outside_rows: list[tuple[str, ...]],
) -> None:
    api = _api()
    rows = [
        (
            "ALPHA",
            "Alpha",
            "S",
            "D",
            "23-Aug-2026 00:00:00",
            "2026-08-23 00:00:00",
            "23-Aug-2026 00:00:00",
            "00:00:00",
            "https://nsearchives.nseindia.com/corporate/alpha.pdf",
        ),
        *outside_rows,
    ]
    parsed = _parse(api, _artifact(rows))
    assert parsed.evidence_state == "PARSED"
    assert _project(api, _artifact(rows)).evidence_state == "PROJECTED"


def test_retained_result_exposes_required_local_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, _project(api), lease, _artifact())
    assert retained.contract_version == api.CONTRACT_VERSION
    assert retained.source_url == _SOURCE_URL
    assert retained.nse_attribution == "NSE"
    assert retained.source_segment == "Equity"
    assert retained.source_window == "1D"
    assert retained.source_filename == _FILENAME
    assert retained.licence_policy_identity == "nse-manual-download-owner-private-v1"
    assert retained.cohort_identity_sha256
    assert retained.cohort_size == retained.member_count == 2
    assert "ALPHA" not in repr(retained)


def test_archive_rejects_unsafe_directory_and_named_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    snapshot = _project(api)
    with _lease(tmp_path) as lease:
        retained = _retain(api, tmp_path, snapshot, lease, _artifact())
        root = tmp_path / ".current-event-notice-v1"
        root.chmod(0o755)
        _failure(
            _retain(api, tmp_path, snapshot, lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_ARCHIVE_FAILED",
        )
        root.chmod(0o700)
        raw_path = root / f"{retained.artifact_identity_sha256}.raw.csv"
        replacement = root / "replacement"
        replacement.write_bytes(raw_path.read_bytes())
        os.replace(replacement, raw_path)
        _failure(
            _retain(api, tmp_path, snapshot, lease, _artifact()),
            "INSUFFICIENT_EVIDENCE",
            "EVENT_ARCHIVE_FAILED",
        )


@pytest.mark.parametrize(
    ("changes", "state", "reason"),
    [
        (
            {"source_url": "https://example.invalid/"},
            "UNSUPPORTED_CAPABILITY",
            "EVENT_SOURCE_MISMATCH",
        ),
        ({"source_segment": "Debt"}, "UNSUPPORTED_CAPABILITY", "EVENT_SOURCE_MISMATCH"),
        ({"source_window": "7D"}, "UNSUPPORTED_CAPABILITY", "EVENT_SOURCE_MISMATCH"),
        (
            {"licence_policy_identity": "other"},
            "UNSUPPORTED_CAPABILITY",
            "EVENT_SOURCE_UNAUTHORIZED",
        ),
    ],
)
def test_source_and_licence_admission_failures_are_typed(
    changes: dict[str, object], state: str, reason: str
) -> None:
    api = _api()
    _failure(_parse(api, _artifact(), **changes), state, reason)


@pytest.mark.parametrize(
    "raw",
    [
        b"\xef\xbb\xbf" + b"x" * 4_194_302,
        _artifact(
            [
                (
                    "ALPHA",
                    "A" * 32_769,
                    "S",
                    "D",
                    "23-Aug-2026 00:00:00",
                    "2026-08-23 00:00:00",
                    "23-Aug-2026 00:00:00",
                    "00:00:00",
                    "https://nsearchives.nseindia.com/corporate/a.pdf",
                )
            ]
        ),
        _artifact(
            [
                (
                    "X",
                    "A",
                    "S",
                    "D",
                    "23-Aug-2026 00:00:00",
                    "2026-08-23 00:00:00",
                    "23-Aug-2026 00:00:00",
                    "00:00:00",
                    "https://nsearchives.nseindia.com/corporate/a.pdf",
                )
            ]
            * 10_001
        ),
    ],
)
def test_declared_raw_row_and_field_bounds_are_typed(raw: bytes) -> None:
    api = _api()
    _failure(_parse(api, raw), "MALFORMED_EVIDENCE", "EVENT_BOUNDS_EXCEEDED")


@pytest.mark.parametrize(
    "rows",
    [
        [
            (
                "ALPHA",
                "Alpha",
                "S",
                "D",
                "23-Aug-2026 24:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/a.pdf",
            )
        ],
        [
            (
                "ALPHA",
                "Alpha",
                "S",
                "D",
                "23-Aug-2026 00:00:00",
                "2026-08-23 00:00:00",
                "23-Aug-2026 00:00:00",
                "99:60:00",
                "https://nsearchives.nseindia.com/corporate/a.pdf",
            )
        ],
    ],
)
def test_invalid_literal_workflow_times_and_difference_are_typed(
    rows: list[tuple[str, ...]],
) -> None:
    api = _api()
    _failure(_parse(api, _artifact(rows)), "MALFORMED_EVIDENCE", "EVENT_TIME_MALFORMED")


def test_duplicate_supplied_symbol_and_forged_out_of_cohort_snapshot_are_typed() -> (
    None
):
    api = _api()
    parsed = _parse(api, _artifact())
    duplicate = (_members(api, 1)[0], _members(api, 1)[0])
    _failure(
        api.project_current_supplied_cohort_event_notices_v1(parsed, duplicate),
        "MALFORMED_EVIDENCE",
        "EVENT_SYMBOL_AMBIGUOUS",
    )
    snapshot = _project(api)
    alpha = snapshot.members[0]
    outside = api.CurrentEventNoticeV1(
        alpha.member,
        "OUTSIDE",
        "Outside",
        "S",
        "D",
        "23-Aug-2026 00:00:00",
        "2026-08-23 00:00:00",
        "23-Aug-2026 00:00:00",
        "00:00:00",
        "https://nsearchives.nseindia.com/corporate/outside.pdf",
        "0" * 64,
        "1" * 64,
    )
    forged = _forge_snapshot(
        api,
        snapshot,
        members=(
            api.CurrentEventNoticeMemberResultV1(
                alpha.member, "NOTICES_ADMITTED", (outside,)
            ),
            snapshot.members[1],
        ),
    )
    assert api._snapshot_out_of_cohort(forged) == "EVENT_OUT_OF_COHORT"


def test_in_contract_amplified_snapshot_uses_separate_archive_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: _KNOWN_AT)
    rows = [
        (
            "ALPHA",
            "A" * 128,
            "S",
            str(index),
            "23-Aug-2026 00:00:00",
            "2026-08-23 00:00:00",
            "23-Aug-2026 00:00:00",
            "00:00:00",
            f"https://nsearchives.nseindia.com/corporate/a{index}.pdf",
        )
        for index in range(10_000)
    ]
    raw = _artifact(rows)
    snapshot = _project(api, raw)
    assert len(raw) <= 4_194_304
    assert len(snapshot.canonical_json_bytes()) > 8_388_608
    with _lease(tmp_path) as lease:
        assert _retain(api, tmp_path, snapshot, lease, raw).evidence_state == "RETAINED"
