"""Manual support for the one-attempt ARK-69 live gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from typing import Final

from ark92_benchmark_baseline_collection import (
    _artifact_path,
    _ArtifactCliFailure,
    _capture_source_identity,
    _expected_source_identity,
    _path_entry_exists,
    _publish_no_overwrite,
    _source_identity_matches,
    _verify_loaded_module_snapshot,
)
from dotenv import dotenv_values

from swing_trading_ai_assistant.market_data.credentials import (
    AccessToken,
    EnvironmentAccessTokenProvider,
)
from swing_trading_ai_assistant.market_data.download_preparation import (
    CanonicalFileScheduleSourceV1,
    DownloadPreparationRequestV1,
    DownloadPreparationServiceV1,
)
from swing_trading_ai_assistant.market_data.historical import UpstoxV3HistoricalClient
from swing_trading_ai_assistant.market_data.http import (
    DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES,
    UrllibHttpTransport,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotClientV1,
)
from swing_trading_ai_assistant.market_data.instruments import (
    DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
)
from swing_trading_ai_assistant.market_data.live_gate import (
    LazyTappedUpstoxSessionFactoryV1,
    LiveGateServiceV1,
    LiveGateTerminalV1,
)
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.range_ingestion import IngestionCoordinator
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
)

_IST: Final = timezone(timedelta(hours=5, minutes=30))
_HEX_40: Final = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64: Final = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_CODE: Final = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_INSTANT: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z"
)
_SCHEMA_VERSION: Final = "ark69-live-gate-receipt-v1"
_MAX_JSON_NESTING: Final = 64


@dataclass(frozen=True, slots=True)
class LiveGateReceipt:
    """The bounded public-safe terminal evidence for one manual invocation."""

    result: str
    code: str
    request_count: int
    provider_attempt_count: int
    raw_count: int
    normalized_count: int
    selected_count: int
    mismatch_count: int
    comparison_passed: bool
    schedule_digest: str | None
    schedule_version: int | None
    schedule_as_of: str | None
    checksum: str | None
    first_ts: str | None
    last_ts: str | None
    source_revision: str
    policy_version: str

    def __post_init__(self) -> None:
        counts = (
            self.request_count,
            self.provider_attempt_count,
            self.raw_count,
            self.normalized_count,
            self.selected_count,
            self.mismatch_count,
        )
        verified = self.result == "VERIFIED"
        schedule_present = (
            self.schedule_digest is not None
            and self.schedule_version == 2
            and self.schedule_as_of is not None
        )
        sealed_present = (
            self.checksum is not None
            and self.first_ts is not None
            and self.last_ts is not None
        )
        if (
            self.result
            not in {"VERIFIED", "FAILED", "REJECTED", "CANCELLED", "BLOCKED"}
            or _SAFE_CODE.fullmatch(self.code) is None
            or any(type(value) is not int or value < 0 for value in counts)
            or self.request_count > 1
            or self.provider_attempt_count > 1
            or self.request_count != self.provider_attempt_count
            or self.raw_count > 100_000
            or self.normalized_count > 100_000
            or self.normalized_count > self.raw_count
            or self.selected_count > 10
            or self.selected_count > self.normalized_count
            or self.mismatch_count > self.selected_count
            or type(self.comparison_passed) is not bool
            or not _optional_digest(self.schedule_digest)
            or self.schedule_version not in {None, 2}
            or not _optional_timestamp(self.schedule_as_of)
            or not _optional_digest(self.checksum)
            or not _optional_timestamp(self.first_ts)
            or not _optional_timestamp(self.last_ts)
            or _HEX_40.fullmatch(self.source_revision) is None
            or self.policy_version != "nse-equity-month@v1"
            or not _receipt_shape_is_valid(
                self, schedule_present=schedule_present, sealed_present=sealed_present
            )
            or (
                verified
                and (
                    self.code != "NONE"
                    or self.request_count != 1
                    or self.provider_attempt_count != 1
                    or self.raw_count < 1
                    or self.normalized_count < 1
                    or self.selected_count < 1
                    or self.mismatch_count != 0
                    or not self.comparison_passed
                    or self.schedule_digest is None
                    or not schedule_present
                    or not sealed_present
                )
            )
            or (not verified and self.comparison_passed)
        ):
            raise ValueError("invalid sanitized live gate receipt")

    @classmethod
    def from_terminal(cls, terminal: LiveGateTerminalV1) -> LiveGateReceipt:
        if type(terminal) is not LiveGateTerminalV1:
            raise ValueError("invalid terminal result")
        return cls(**asdict(terminal))


def _receipt_shape_is_valid(
    receipt: LiveGateReceipt, *, schedule_present: bool, sealed_present: bool
) -> bool:
    empty_comparison = (
        receipt.raw_count == 0
        and receipt.normalized_count == 0
        and receipt.selected_count == 0
        and receipt.mismatch_count == 0
        and not receipt.comparison_passed
    )
    no_sealed_fields = (
        receipt.checksum is None
        and receipt.first_ts is None
        and receipt.last_ts is None
    )
    if receipt.result == "VERIFIED":
        return True
    if receipt.result == "REJECTED":
        return (
            receipt.code != "NONE"
            and receipt.request_count == 0
            and empty_comparison
            and not schedule_present
            and no_sealed_fields
        )
    if receipt.result == "BLOCKED":
        return (
            receipt.code != "NONE"
            and receipt.request_count == 0
            and empty_comparison
            and no_sealed_fields
        )
    if receipt.result == "CANCELLED":
        return (
            receipt.code == "CANCELLED"
            and empty_comparison
            and schedule_present
            and no_sealed_fields
        )
    if receipt.result != "FAILED" or receipt.code == "NONE":
        return False
    if receipt.code == "SAMPLE_MISMATCH":
        return (
            receipt.request_count == 1
            and receipt.raw_count >= receipt.normalized_count > 0
            and receipt.selected_count > 0
            and receipt.mismatch_count > 0
            and schedule_present
            and sealed_present
        )
    return empty_comparison and (
        (receipt.request_count == 0 and not schedule_present and no_sealed_fields)
        or (
            receipt.request_count == 1
            and schedule_present
            and receipt.first_ts is None
            and receipt.last_ts is None
        )
    )


def compose_closed_month_schedule(  # noqa: C901 - validates one hostile boundary
    selected_month: date,
    authoritative_snapshot: bytes,
    *,
    source_release: str,
    observed_at: datetime,
) -> ExpectedSessionSchedule:
    """Compose exact v2 evidence from a supplied, bounded NSE CM snapshot.

    The input is deliberately a caller-provided snapshot: this function neither
    acquires calendars nor substitutes a contemporary holiday list.
    """
    if type(selected_month) is not date:
        raise ValueError("invalid schedule input")
    raw, snapshot = _snapshot_bytes(authoritative_snapshot)
    if source_release != f"sha256:{hashlib.sha256(raw).hexdigest()}":
        raise ValueError("invalid schedule input")
    if type(observed_at) is not datetime or observed_at.tzinfo is None:
        raise ValueError("invalid schedule input")
    observed_at = observed_at.astimezone(UTC)
    first = selected_month.replace(day=1)
    after_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = after_month - timedelta(days=1)
    if last >= observed_at.astimezone(_IST).date():
        raise ValueError("selected month is not closed")
    sessions: list[ScheduleSession] = []
    closures: list[ScheduleClosure] = []
    entries = snapshot.get("dates")
    if set(snapshot) != {"dates"} or type(entries) is not list:
        raise ValueError("invalid authoritative calendar")
    seen: set[date] = set()
    for entry in entries:
        if type(entry) is not dict or set(entry) - {"date", "session", "closure"}:
            raise ValueError("invalid authoritative calendar")
        text = entry.get("date")
        if type(text) is not str or _DATE.fullmatch(text) is None:
            raise ValueError("invalid authoritative calendar")
        current = date.fromisoformat(text)
        if current < first or current > last or current in seen:
            raise ValueError("invalid authoritative calendar")
        seen.add(current)
        session = entry.get("session")
        closure = entry.get("closure")
        if type(session) is dict and closure is None:
            if set(session) != {"open_at", "close_at", "kind"}:
                raise ValueError("invalid authoritative calendar")
            sessions.append(
                ScheduleSession(
                    current,
                    _instant(session["open_at"]),
                    _instant(session["close_at"]),
                    _text(session["kind"]),
                )
            )
        elif type(closure) is dict and session is None and set(closure) == {"reason"}:
            closures.append(ScheduleClosure(current, _text(closure["reason"])))
        else:
            raise ValueError("invalid authoritative calendar")
    if seen != {
        first + timedelta(days=index) for index in range((last - first).days + 1)
    }:
        raise ValueError("incomplete authoritative calendar")
    sessions.sort(key=lambda item: item.trade_date)
    closures.sort(key=lambda item: item.trade_date)
    return ExpectedSessionSchedule(
        2,
        "nse-authoritative-calendar",
        source_release,
        observed_at,
        "Asia/Kolkata",
        first,
        last,
        tuple(sessions),
        tuple(closures),
    )


def write_receipt_no_overwrite(output: Path, receipt: LiveGateReceipt) -> None:
    """Write a canonical sanitized receipt once; existing evidence is immutable."""
    if not isinstance(output, Path) or type(receipt) is not LiveGateReceipt:
        raise ValueError("invalid receipt output")
    payload = {"schema_version": _SCHEMA_VERSION, **asdict(receipt)}
    _publish_no_overwrite(output, _receipt_bytes(payload))


def main(argv: list[str] | None = None) -> int:
    """Compose schedule evidence or execute the one immutable live receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="mode", required=True)
    schedule = subcommands.add_parser("compose-schedule")
    schedule.add_argument("--month", required=True)
    schedule.add_argument("--authoritative-calendar", type=Path, required=True)
    schedule.add_argument("--observed-at", required=True)
    schedule.add_argument("--output", type=Path, required=True)
    live = subcommands.add_parser("live-run")
    live.add_argument("--segment", required=True)
    live.add_argument("--symbol", required=True)
    live.add_argument("--from", dest="from_date", required=True)
    live.add_argument("--to", dest="to_date", required=True)
    live.add_argument("--schedule-file", type=Path, required=True)
    live.add_argument("--storage-root", type=Path, required=True)
    live.add_argument("--dotenv-file", type=Path, required=True)
    live.add_argument("--output", type=Path, required=True)
    live.add_argument("--expected-revision", required=True)
    live.add_argument("--expected-tree", required=True)
    arguments = parser.parse_args(argv)
    if arguments.mode == "live-run":
        return _run_live(arguments)
    try:
        snapshot = _read_bounded_regular(
            arguments.authoritative_calendar, required_mode=0o400
        )
        month = date.fromisoformat(arguments.month + "-01")
        observed = datetime.fromisoformat(arguments.observed_at.replace("Z", "+00:00"))
        composed = compose_closed_month_schedule(
            month,
            snapshot,
            source_release="sha256:" + hashlib.sha256(snapshot).hexdigest(),
            observed_at=observed,
        )
        output = arguments.output
        write_schedule_no_overwrite(output, composed)
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        print("live gate failed: SCHEDULE_EVIDENCE_INVALID", file=sys.stderr)
        return 2


def write_schedule_no_overwrite(
    output: Path, schedule: ExpectedSessionSchedule
) -> None:
    """Persist canonical schedule evidence without making any provider request."""
    payload = canonical_schedule_bytes(schedule)
    _publish_no_overwrite(output, payload)


def _run_live(arguments: argparse.Namespace) -> int:
    try:
        output = _artifact_path(arguments.output, "output")
        _admit_source(arguments.expected_revision, arguments.expected_tree)
        if _path_entry_exists(output):
            raise ValueError("live gate receipt already exists")
        from_date = _date(arguments.from_date)
        to_date = _date(arguments.to_date)
        if not _is_full_month(from_date, to_date):
            raise ValueError("live gate requires one complete month")
        clock = _SystemClock()
        service = _build_live_service(arguments, clock)
        terminal = service.run(
            DownloadPreparationRequestV1(
                arguments.segment,
                arguments.symbol,
                from_date,
                to_date,
                arguments.storage_root,
                clock.now(),
            )
        )
        receipt = LiveGateReceipt.from_terminal(terminal)
        write_receipt_no_overwrite(output, receipt)
        sys.stdout.buffer.write(
            _receipt_bytes({"schema_version": _SCHEMA_VERSION, **asdict(receipt)})
        )
        return 0 if terminal.result == "VERIFIED" else 1
    except _ArtifactCliFailure:
        print("live gate failed: SOURCE_ADMISSION_FAILED", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print("live gate failed: EVIDENCE_INVALID", file=sys.stderr)
        return 2


def _build_live_service(
    arguments: argparse.Namespace, clock: _SystemClock
) -> LiveGateServiceV1:
    catalog_transport = UrllibHttpTransport(
        max_body_bytes=DEFAULT_MAX_CATALOG_COMPRESSED_BYTES
    )
    historical_transport = UrllibHttpTransport(
        max_body_bytes=DEFAULT_MAX_HISTORICAL_RESPONSE_BYTES
    )
    preparation = DownloadPreparationServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        CanonicalFileScheduleSourceV1(arguments.schedule_file),
        InstrumentSnapshotClientV1(catalog_transport, clock=clock.now),
        clock=clock,
    )
    sessions = LazyTappedUpstoxSessionFactoryV1(
        UpstoxV3HistoricalClient(historical_transport),
        lambda: _load_token(arguments.dotenv_file),
    )
    return LiveGateServiceV1(
        preparation,
        lambda supplied: IngestionCoordinator(
            session_factory=supplied,
            clock=clock,
            run_id_factory=lambda: "ark69-live-v1",
        ),
        sessions,
        clock=clock,
        source_revision=arguments.expected_revision,
    )


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _load_token(dotenv_file: Path) -> AccessToken:
    encoded = _read_bounded_regular(dotenv_file, maximum=4096, required_mode=0o600)
    values = dotenv_values(stream=StringIO(encoded.decode("utf-8")))
    environment = {
        key: value
        for key, value in values.items()
        if type(key) is str and type(value) is str
    }
    return EnvironmentAccessTokenProvider(environment).get_access_token()


def _admit_source(revision: object, tree: object) -> None:
    expected = _expected_source_identity(revision, tree)
    actual = _capture_source_identity()
    if actual != expected or not _source_identity_matches(actual):
        raise _ArtifactCliFailure("SOURCE_MISMATCH")
    _verify_loaded_module_snapshot(actual)


def _date(value: object) -> date:
    if (
        type(value) is not str
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
    ):
        raise ValueError("invalid date")
    return date.fromisoformat(value)


def _is_full_month(from_date: date, to_date: date) -> bool:
    after = (from_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    return from_date.day == 1 and to_date == after - timedelta(days=1)


def _receipt_bytes(payload: Mapping[str, object]) -> bytes:
    encoded = (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if len(encoded) > 16_384:
        raise ValueError("live gate receipt exceeds limit")
    return encoded


def _optional_digest(value: object) -> bool:
    return value is None or (
        type(value) is str and _HEX_64.fullmatch(value) is not None
    )


def _optional_timestamp(value: object) -> bool:
    if value is None:
        return True
    if type(value) is not str or len(value) != 27 or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _read_bounded_regular(
    path: Path, *, maximum: int = 262_144, required_mode: int | None = None
) -> bytes:
    if not path.is_absolute():
        raise ValueError("input path must be absolute")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_size < 1
            or before.st_size > maximum
            or (
                required_mode is not None
                and stat.S_IMODE(before.st_mode) != required_mode
            )
        ):
            raise ValueError("invalid bounded input")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        encoded = b"".join(chunks)
        after = os.fstat(descriptor)
        entry = os.stat(path, follow_symlinks=False)
        identity = _file_identity(before)
        if (
            len(encoded) > maximum
            or identity != _file_identity(after)
            or identity != _file_identity(entry)
            or (
                required_mode is not None
                and stat.S_IMODE(after.st_mode) != required_mode
            )
        ):
            raise ValueError("bounded input changed")
        return encoded
    finally:
        os.close(descriptor)


def _file_identity(
    value: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
        stat.S_IMODE(value.st_mode),
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
    )


def _snapshot_bytes(
    value: bytes,
) -> tuple[bytes, Mapping[str, object]]:
    if type(value) is not bytes or not 1 <= len(value) <= 262_144:
        raise ValueError("invalid authoritative calendar")
    raw = value
    try:
        text = raw.decode("utf-8", errors="strict")
        _validate_json_nesting(text)
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        MemoryError,
        ValueError,
    ) as error:
        raise ValueError("invalid authoritative calendar") from error
    if type(parsed) is not dict:
        raise ValueError("invalid authoritative calendar")
    return raw, parsed


def _validate_json_nesting(text: str) -> None:  # noqa: C901 - hostile JSON scanner
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > _MAX_JSON_NESTING:
                raise ValueError("invalid authoritative calendar")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("invalid authoritative calendar")
    if depth != 0 or in_string or escaped:
        raise ValueError("invalid authoritative calendar")


def _instant(value: object) -> datetime:
    if type(value) is not str or _INSTANT.fullmatch(value) is None:
        raise ValueError("invalid authoritative calendar")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid authoritative calendar")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> object:
    raise ValueError("invalid authoritative calendar")


def _text(value: object) -> str:
    if type(value) is not str or not value.isascii() or not value:
        raise ValueError("invalid authoritative calendar")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
