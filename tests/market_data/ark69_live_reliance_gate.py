"""Manual support for the one-attempt ARK-69 live gate."""

from __future__ import annotations

import argparse
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
_DATE_TEXT: Final = re.compile(r"\d{2}-[A-Za-z]{3}-\d{4}\Z")
_SAFE_CODE: Final = re.compile(r"[A-Z][A-Z0-9_]{0,79}\Z")
_SCHEMA_VERSION: Final = "ark69-live-gate-receipt-v1"


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
        if (
            self.result
            not in {"VERIFIED", "FAILED", "REJECTED", "CANCELLED", "BLOCKED"}
            or _SAFE_CODE.fullmatch(self.code) is None
            or any(type(value) is not int or value < 0 for value in counts)
            or self.request_count > 1
            or self.provider_attempt_count > 1
            or self.raw_count > 100_000
            or self.normalized_count > 100_000
            or self.selected_count > 10
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
                    or self.schedule_version != 2
                    or self.schedule_as_of is None
                    or self.checksum is None
                    or self.first_ts is None
                    or self.last_ts is None
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


def compose_closed_month_schedule(
    selected_month: date,
    holiday_master_cm: Mapping[str, object],
    *,
    source_release: str,
    observed_at: datetime,
) -> ExpectedSessionSchedule:
    """Compose exact v2 evidence from a supplied, bounded NSE CM snapshot.

    The input is deliberately a caller-provided snapshot: this function neither
    acquires calendars nor substitutes a contemporary holiday list.
    """
    if type(selected_month) is not date or type(holiday_master_cm) is not dict:
        raise ValueError("invalid schedule input")
    if (
        type(source_release) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", source_release) is None
    ):
        raise ValueError("invalid schedule input")
    if type(observed_at) is not datetime or observed_at.tzinfo is None:
        raise ValueError("invalid schedule input")
    observed_at = observed_at.astimezone(UTC)
    first = selected_month.replace(day=1)
    after_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = after_month - timedelta(days=1)
    if last >= observed_at.astimezone(_IST).date():
        raise ValueError("selected month is not closed")
    holidays = _cm_holidays(holiday_master_cm, first, last)
    sessions: list[ScheduleSession] = []
    closures: list[ScheduleClosure] = []
    current = first
    while current <= last:
        if current.weekday() >= 5:
            closures.append(ScheduleClosure(current, "weekend"))
        elif current in holidays:
            closures.append(ScheduleClosure(current, "official-holiday"))
        else:
            sessions.append(
                ScheduleSession(
                    current,
                    datetime(
                        current.year, current.month, current.day, 3, 45, tzinfo=UTC
                    ),
                    datetime(
                        current.year, current.month, current.day, 10, 0, tzinfo=UTC
                    ),
                    "nse-equity-regular",
                )
            )
        current += timedelta(days=1)
    return ExpectedSessionSchedule(
        2,
        "nse-holiday-master-cm",
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
    schedule.add_argument("--holiday-master-cm", type=Path, required=True)
    schedule.add_argument("--source-release", required=True)
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
        snapshot = json.loads(_read_bounded_regular(arguments.holiday_master_cm))
        month = date.fromisoformat(arguments.month + "-01")
        observed = datetime.fromisoformat(arguments.observed_at.replace("Z", "+00:00"))
        composed = compose_closed_month_schedule(
            month,
            snapshot,
            source_release=arguments.source_release,
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
            or before.st_uid != os.getuid()
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
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        if (
            len(encoded) > maximum
            or identity
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or identity
            != (entry.st_dev, entry.st_ino, entry.st_size, entry.st_mtime_ns)
        ):
            raise ValueError("bounded input changed")
        return encoded
    finally:
        os.close(descriptor)


def _cm_holidays(snapshot: Mapping[str, object], first: date, last: date) -> set[date]:
    entries = snapshot.get("CM")
    if type(entries) is not list:
        raise ValueError("invalid official CM holiday snapshot")
    holidays: set[date] = set()
    for entry in entries:
        if type(entry) is not dict:
            raise ValueError("invalid official CM holiday snapshot")
        text = entry.get("tradingDate")
        if type(text) is not str or _DATE_TEXT.fullmatch(text) is None:
            raise ValueError("invalid official CM holiday snapshot")
        holiday = datetime.strptime(text, "%d-%b-%Y").date()
        if first <= holiday <= last:
            holidays.add(holiday)
    return holidays


if __name__ == "__main__":
    raise SystemExit(main())
