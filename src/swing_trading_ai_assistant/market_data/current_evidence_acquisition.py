"""Bounded official current-evidence acquisition for the Sprint-14 working slice."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Final, Protocol, TypeGuard, cast
from urllib.request import HTTPCookieProcessor, Request, build_opener
from weakref import ReferenceType, ref
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.current_event_notice import (
    CURRENT_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1,
    EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    CurrentEventNoticeFailureV1,
    CurrentEventNoticeInputV1,
    parse_current_event_notice_artifact_v1,
)
from swing_trading_ai_assistant.market_data.current_evidence_acquisition_runtime_identity_manifest import (
    CURRENT_EVIDENCE_ACQUISITION_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.market_data.current_industry_classification import (
    CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
    CurrentIndustryClassificationFailureV1,
    CurrentIndustryClassificationInputV1,
    parse_current_industry_artifact_v1,
)
from swing_trading_ai_assistant.market_data.current_industry_classification import (
    CURRENT_INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256 as INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256,
)
from swing_trading_ai_assistant.market_data.http import (
    DEFAULT_USER_AGENT,
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransport,
    HttpTransportError,
    SameOriginAuthorizationRedirectHandler,
    UrllibHttpTransport,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
    schedule_digest,
)

INDUSTRY_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
)
NSE_ANNOUNCEMENTS_PAGE_URL: Final = (
    "https://www.nseindia.com/companies-listing/"
    "corporate-filings-announcements?tabIndex=equity"
)
NSE_ANNOUNCEMENTS_API_URL: Final = (
    "https://www.nseindia.com/api/corporate-announcements"
)
UPSTOX_HOLIDAYS_URL: Final = "https://api.upstox.com/v2/market/holidays"
UPSTOX_TIMINGS_URL: Final = "https://api.upstox.com/v2/market/timings"
NSE_HOLIDAY_MASTER_URL: Final = "https://www.nseindia.com/api/holiday-master"
SCHEDULE_SOURCE: Final = "nse-upstox-composed-calendar"
SCHEDULE_COMPOSITION_VERSION: Final = "nse-equity-composed-calendar@v1"
INDUSTRY_ACQUISITION_METHOD: Final = "BOUNDED_OFFICIAL_FETCH"
EVENT_LICENCE_POLICY_IDENTITY: Final = CURRENT_EVENT_NOTICE_LICENCE_POLICY_IDENTITY_V1

_MAX_BODY_BYTES: Final = 4_194_304
_MAX_INDUSTRY_BYTES: Final = 1_048_576
_MAX_PAGE_BYTES: Final = 1_048_576
_MAX_SCHEDULE_BYTES: Final = 1_048_576
_MAX_EVENT_BYTES: Final = 4_194_304
_MAX_COOKIES: Final = 32
_MAX_COOKIE_BYTES: Final = 8_192
_MAX_COVERAGE_DAYS: Final = 62
_MAX_OBSERVATIONS: Final = 50
_MAX_URL_BYTES: Final = 2_048
_MAX_PROVENANCE_HEADER_BYTES: Final = 32_768
_MAX_JSON_DEPTH: Final = 8
_MAX_JSON_NODES: Final = 20_000
_MAX_JSON_ARRAY_ITEMS: Final = 5_000
_MAX_NSE_HOLIDAY_ROWS: Final = 1_000
_MAX_CALENDAR_OBSERVATIONS: Final = 34
_MAX_SHARED_CALENDAR_OBSERVATIONS: Final = _MAX_OBSERVATIONS - 3
_MAX_CALENDAR_EVIDENCE_BYTES: Final = 48_000_000
_MAX_CURRENT_CALENDAR_COVERAGE_DAYS: Final = 32
_NSE_HOLIDAY_SEGMENTS: Final = (
    "CBM",
    "CD",
    "CM",
    "CMOT",
    "COM",
    "EGR",
    "FO",
    "IRD",
    "MF",
    "NDM",
    "NTRP",
    "SLBS",
)
_TIMEOUT_SECONDS: Final = 15.0
_IST: Final = ZoneInfo("Asia/Kolkata")
_NSE_DATE: Final = re.compile(r"(\d{2})-([A-Z][a-z]{2})-(\d{4})\Z")
_EVENT_FILENAME: Final = re.compile(
    r"CF-AN-equities-(\d{2})-(\d{2})-(\d{4})-to-"
    r"(\d{2})-(\d{2})-(\d{4})\.csv\Z"
)
_CONTENT_DISPOSITION: Final = re.compile(
    r'attachment\s*;\s*filename=(?:"([^"]+)"|([A-Za-z0-9._-]+))\Z',
    re.IGNORECASE,
)
_PROVENANCE_HEADERS: Final = frozenset(
    {
        "content-type",
        "content-encoding",
        "content-length",
        "content-disposition",
        "date",
        "etag",
        "last-modified",
    }
)
_WEEKDAYS: Final = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_MONTHS: Final = {
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
}
_RECOGNIZED_HOLIDAY_TYPES: Final = frozenset(
    {"TRADING_HOLIDAY", "SETTLEMENT_HOLIDAY", "SPECIAL_TIMING"}
)
_REGULAR_OPEN: Final = time(9, 15)
_REGULAR_CLOSE: Final = time(15, 30)


class CurrentEvidenceAcquisitionFailureCode(StrEnum):
    """Closed sanitized acquisition and composition failures."""

    HTTP_FAILURE = "HTTP_FAILURE"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    CONTENT_TYPE_MISMATCH = "CONTENT_TYPE_MISMATCH"
    COOKIE_BOUNDS_EXCEEDED = "COOKIE_BOUNDS_EXCEEDED"
    SOURCE_MALFORMED = "SOURCE_MALFORMED"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    SPECIAL_SESSION_UNCORROBORATED = "SPECIAL_SESSION_UNCORROBORATED"
    ACQUISITION_CUTOFF_EXCEEDED = "ACQUISITION_CUTOFF_EXCEEDED"
    ACQUISITION_DATE_ROLLOVER = "ACQUISITION_DATE_ROLLOVER"


class CurrentEvidenceAcquisitionError(RuntimeError):
    """A bounded acquisition failed without carrying response narrative."""

    def __init__(self, code: CurrentEvidenceAcquisitionFailureCode | str) -> None:
        try:
            parsed = CurrentEvidenceAcquisitionFailureCode(code)
        except ValueError:
            parsed = CurrentEvidenceAcquisitionFailureCode.SOURCE_MALFORMED
        self.code = parsed
        super().__init__(parsed.value)


class TrustedClockV1(Protocol):
    def __call__(self) -> datetime: ...


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class OfficialHttpObservationV1:
    """Read-only identity-bound response provenance; cookie values stay private."""

    request_url: str
    response_url: str
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes = field(repr=False)
    known_at: datetime
    cookie_count: int
    cookie_aggregate_bytes: int
    observation_identity_sha256: str

    def __init__(self) -> None:
        raise TypeError("official HTTP observations are acquisition-minted")

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def body_byte_count(self) -> int:
        return len(self.body)

    def identity_value(self) -> dict[str, object]:
        return {
            "body_byte_count": len(self.body),
            "body_sha256": hashlib.sha256(self.body).hexdigest(),
            "cookie_aggregate_bytes": self.cookie_aggregate_bytes,
            "cookie_count": self.cookie_count,
            "headers": [list(item) for item in self.headers],
            "known_at": _instant(self.known_at),
            "request_url": self.request_url,
            "response_url": self.response_url,
            "status": self.status,
        }


def _mint_observation(
    *,
    request_url: str,
    response_url: str,
    status: int,
    headers: tuple[tuple[str, str], ...],
    body: bytes,
    known_at: datetime,
    cookie_count: int,
    cookie_aggregate_bytes: int,
) -> OfficialHttpObservationV1:
    header_bytes = sum(
        len(name.encode("latin-1")) + len(value.encode("latin-1"))
        for name, value in headers
    )
    if (
        not _safe_url(request_url)
        or response_url != request_url
        or type(status) is not int
        or status != 200
        or type(headers) is not tuple
        or len(headers) > len(_PROVENANCE_HEADERS)
        or len({name.casefold() for name, _ in headers}) != len(headers)
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            or item[0].casefold() not in _PROVENANCE_HEADERS
            for item in headers
        )
        or header_bytes > _MAX_PROVENANCE_HEADER_BYTES
        or type(body) is not bytes
        or not 1 <= len(body) <= _MAX_BODY_BYTES
        or not _is_utc(known_at)
        or not 2000 <= known_at.year <= 2100
        or type(cookie_count) is not int
        or type(cookie_aggregate_bytes) is not int
        or not 0 <= cookie_count <= _MAX_COOKIES
        or not 0 <= cookie_aggregate_bytes <= _MAX_COOKIE_BYTES
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    result = object.__new__(OfficialHttpObservationV1)
    values: dict[str, object] = {
        "request_url": request_url,
        "response_url": response_url,
        "status": status,
        "headers": headers,
        "body": body,
        "known_at": known_at,
        "cookie_count": cookie_count,
        "cookie_aggregate_bytes": cookie_aggregate_bytes,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    object.__setattr__(
        result, "observation_identity_sha256", _identity(result.identity_value())
    )
    _register_official_observation(result, result.observation_identity_sha256)
    return result


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class CurrentEvidenceObservationsV1:
    """Named, bounded observations in their exact request-arrival order."""

    industry: OfficialHttpObservationV1
    announcements_page: OfficialHttpObservationV1
    event_csv: OfficialHttpObservationV1
    upstox_current_year_holidays: OfficialHttpObservationV1
    nse_holiday_masters: tuple[OfficialHttpObservationV1, ...]
    upstox_prior_year_timings: tuple[OfficialHttpObservationV1, ...]

    def __init__(self) -> None:
        raise TypeError("observation sets are acquisition-minted")

    @property
    def all(self) -> tuple[OfficialHttpObservationV1, ...]:
        return (
            self.industry,
            self.announcements_page,
            self.event_csv,
            self.upstox_current_year_holidays,
            *self.nse_holiday_masters,
            *self.upstox_prior_year_timings,
        )

    def __iter__(self) -> Iterator[OfficialHttpObservationV1]:
        return iter(self.all)

    def __len__(self) -> int:
        return len(self.all)


def _mint_observation_set(
    observations: tuple[OfficialHttpObservationV1, ...],
    *,
    holiday_master_count: int,
) -> CurrentEvidenceObservationsV1:
    if (
        type(observations) is not tuple
        or type(holiday_master_count) is not int
        or holiday_master_count not in (1, 2)
        or not 5 <= len(observations) <= _MAX_OBSERVATIONS
        or not all(_official_observation_is_exact_v1(item) for item in observations)
        or len({item.observation_identity_sha256 for item in observations})
        != len(observations)
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    result = object.__new__(CurrentEvidenceObservationsV1)
    masters_end = 4 + holiday_master_count
    values: dict[str, object] = {
        "industry": observations[0],
        "announcements_page": observations[1],
        "event_csv": observations[2],
        "upstox_current_year_holidays": observations[3],
        "nse_holiday_masters": observations[4:masters_end],
        "upstox_prior_year_timings": observations[masters_end:],
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    _register_observation_set(result, _observation_set_binding(result))
    return result


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class CurrentCalendarEvidenceObservationsV1:
    """Exact calendar-source observations without unrelated capability inputs."""

    upstox_current_year_holidays: OfficialHttpObservationV1
    nse_holiday_masters: tuple[OfficialHttpObservationV1, ...]
    upstox_prior_year_timings: tuple[OfficialHttpObservationV1, ...]

    def __init__(self) -> None:
        raise TypeError("calendar observation sets are acquisition-minted")

    @property
    def all(self) -> tuple[OfficialHttpObservationV1, ...]:
        return (
            self.upstox_current_year_holidays,
            *self.nse_holiday_masters,
            *self.upstox_prior_year_timings,
        )

    def __iter__(self) -> Iterator[OfficialHttpObservationV1]:
        return iter(self.all)

    def __len__(self) -> int:
        return len(self.all)


def _mint_calendar_observation_set(
    observations: tuple[OfficialHttpObservationV1, ...],
    *,
    holiday_master_count: int,
) -> CurrentCalendarEvidenceObservationsV1:
    if (
        type(observations) is not tuple
        or type(holiday_master_count) is not int
        or holiday_master_count not in (1, 2)
        or not 2 <= len(observations) <= _MAX_SHARED_CALENDAR_OBSERVATIONS
        or not all(_official_observation_is_exact_v1(item) for item in observations)
        or len({item.observation_identity_sha256 for item in observations})
        != len(observations)
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    result = object.__new__(CurrentCalendarEvidenceObservationsV1)
    masters_end = 1 + holiday_master_count
    values: dict[str, object] = {
        "upstox_current_year_holidays": observations[0],
        "nse_holiday_masters": observations[1:masters_end],
        "upstox_prior_year_timings": observations[masters_end:],
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    _register_observation_set(result, _calendar_observation_set_binding(result))
    return result


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class CurrentCalendarEvidenceBundleV1:
    """Private reproducible calendar evidence and its canonical schedule."""

    observations: CurrentCalendarEvidenceObservationsV1
    source_manifest_bytes: bytes = field(repr=False)
    source_manifest_sha256: str
    schedule: ExpectedSessionSchedule
    schedule_evidence_sha256: str
    runtime_code_identity_sha256: str

    def __init__(self) -> None:
        raise TypeError("current calendar evidence bundles are acquisition-minted")

    def canonical_json_bytes(self) -> bytes:
        """Serialize one bounded private evidence record for exact re-admission."""
        if not validate_current_calendar_evidence_bundle_v1(self):
            raise ValueError("invalid current calendar evidence")
        raw = _canonical(
            {
                "observations": [
                    _calendar_observation_value(item) for item in self.observations
                ],
                "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
                "schedule_b64": _base64_encode(canonical_schedule_bytes(self.schedule)),
                "schedule_evidence_sha256": self.schedule_evidence_sha256,
                "schema_version": 1,
                "source_manifest_b64": _base64_encode(self.source_manifest_bytes),
                "source_manifest_sha256": self.source_manifest_sha256,
            }
        )
        if len(raw) > _MAX_CALENDAR_EVIDENCE_BYTES:
            raise ValueError("invalid current calendar evidence")
        return raw


def _mint_calendar_bundle(
    *,
    observations: CurrentCalendarEvidenceObservationsV1,
    source_manifest_bytes: bytes,
    schedule: ExpectedSessionSchedule,
) -> CurrentCalendarEvidenceBundleV1:
    manifest_sha256 = hashlib.sha256(source_manifest_bytes).hexdigest()
    runtime_identity = current_evidence_acquisition_runtime_code_identity_v1()
    if (
        not _calendar_observation_set_is_exact_v1(observations)
        or type(source_manifest_bytes) is not bytes
        or not 1 <= len(source_manifest_bytes) <= _MAX_SCHEDULE_BYTES
        or type(schedule) is not ExpectedSessionSchedule
        or (schedule.covered_to - schedule.covered_from).days + 1
        > _MAX_CURRENT_CALENDAR_COVERAGE_DAYS
        or schedule.source != SCHEDULE_SOURCE
        or schedule.source_release != f"composed-calendar@v1={manifest_sha256}"
        or any(item.known_at > schedule.as_of for item in observations)
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    result = object.__new__(CurrentCalendarEvidenceBundleV1)
    values: dict[str, object] = {
        "observations": observations,
        "source_manifest_bytes": source_manifest_bytes,
        "source_manifest_sha256": manifest_sha256,
        "schedule": schedule,
        "schedule_evidence_sha256": schedule_digest(schedule),
        "runtime_code_identity_sha256": runtime_identity,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    _register_evidence_bundle(result, _calendar_bundle_binding(result))
    if not validate_current_calendar_evidence_bundle_v1(result):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    return result


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class CurrentSprint14EvidenceBundleV1:
    """Read-only coherent parser inputs and composed retained schedule."""

    observations: CurrentEvidenceObservationsV1
    source_manifest_bytes: bytes = field(repr=False)
    source_manifest_sha256: str
    schedule: ExpectedSessionSchedule
    schedule_evidence_sha256: str
    runtime_code_identity_sha256: str
    industry_input: CurrentIndustryClassificationInputV1
    industry_artifact: bytes = field(repr=False)
    event_input: CurrentEventNoticeInputV1
    event_artifact: bytes = field(repr=False)

    def __init__(self) -> None:
        raise TypeError("current evidence bundles are acquisition-minted")


def _mint_bundle(
    *,
    observations: CurrentEvidenceObservationsV1,
    source_manifest_bytes: bytes,
    schedule: ExpectedSessionSchedule,
    industry_input: CurrentIndustryClassificationInputV1,
    event_input: CurrentEventNoticeInputV1,
) -> CurrentSprint14EvidenceBundleV1:
    manifest_sha256 = hashlib.sha256(source_manifest_bytes).hexdigest()
    runtime_identity = current_evidence_acquisition_runtime_code_identity_v1()
    if (
        not _observation_set_is_exact_v1(observations)
        or type(source_manifest_bytes) is not bytes
        or not 1 <= len(source_manifest_bytes) <= _MAX_SCHEDULE_BYTES
        or type(schedule) is not ExpectedSessionSchedule
        or schedule.source != SCHEDULE_SOURCE
        or schedule.source_release != f"composed-calendar@v1={manifest_sha256}"
        or any(item.known_at > schedule.as_of for item in observations)
        or observations.industry.body_sha256 != industry_input.artifact_sha256
        or observations.event_csv.body_sha256 != event_input.artifact_identity_sha256
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    result = object.__new__(CurrentSprint14EvidenceBundleV1)
    values: dict[str, object] = {
        "observations": observations,
        "source_manifest_bytes": source_manifest_bytes,
        "source_manifest_sha256": manifest_sha256,
        "schedule": schedule,
        "schedule_evidence_sha256": schedule_digest(schedule),
        "runtime_code_identity_sha256": runtime_identity,
        "industry_input": industry_input,
        "industry_artifact": observations.industry.body,
        "event_input": event_input,
        "event_artifact": observations.event_csv.body,
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    _register_evidence_bundle(result, _bundle_binding(result))
    if not validate_current_sprint14_evidence_bundle_v1(result):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    return result


def _acquisition_registry_boundary():  # noqa: C901
    """Create closure-private mint registries with immutable mint-time bindings."""
    observation_registry: dict[int, tuple[ReferenceType[object], object]] = {}
    observation_set_registry: dict[int, tuple[ReferenceType[object], object]] = {}
    bundle_registry: dict[int, tuple[ReferenceType[object], object]] = {}

    def register(
        registry: dict[int, tuple[ReferenceType[object], object]],
        value: object,
        binding: object,
    ) -> None:
        key = id(value)

        def discard(reference: ReferenceType[object]) -> None:
            current = registry.get(key)
            if current is not None and current[0] is reference:
                registry.pop(key, None)

        registry[key] = (ref(value, discard), binding)

    def registered(
        registry: dict[int, tuple[ReferenceType[object], object]],
        value: object,
        binding: object,
    ) -> bool:
        current = registry.get(id(value))
        return current is not None and current[0]() is value and current[1] == binding

    def register_observation(value: object, binding: object) -> None:
        register(observation_registry, value, binding)

    def observation_registered(value: object, binding: object) -> bool:
        return registered(observation_registry, value, binding)

    def register_observation_set(value: object, binding: object) -> None:
        register(observation_set_registry, value, binding)

    def observation_set_registered(value: object, binding: object) -> bool:
        return registered(observation_set_registry, value, binding)

    def register_bundle(value: object, binding: object) -> None:
        register(bundle_registry, value, binding)

    def bundle_registered(value: object, binding: object) -> bool:
        return registered(bundle_registry, value, binding)

    return (
        register_observation,
        observation_registered,
        register_observation_set,
        observation_set_registered,
        register_bundle,
        bundle_registered,
    )


(
    _register_official_observation,
    _official_observation_registered,
    _register_observation_set,
    _observation_set_registered,
    _register_evidence_bundle,
    _evidence_bundle_registered,
) = _acquisition_registry_boundary()


def _observation_required_spec_v1(  # noqa: C901
    url: object,
) -> tuple[int, str, bool] | None:
    if type(url) is not str:
        return None
    fixed = {
        INDUSTRY_URL: (_MAX_INDUSTRY_BYTES, "text/csv", False),
        NSE_ANNOUNCEMENTS_PAGE_URL: (_MAX_PAGE_BYTES, "text/html", False),
        UPSTOX_HOLIDAYS_URL: (_MAX_SCHEDULE_BYTES, "application/json", False),
    }
    if url in fixed:
        return fixed[url]
    event = re.fullmatch(
        re.escape(NSE_ANNOUNCEMENTS_API_URL)
        + r"\?index=equities&from_date=(\d{2}-\d{2}-\d{4})"
        + r"&to_date=(\d{2}-\d{2}-\d{4})&csv=true",
        url,
    )
    if event is not None:
        try:
            range_from = datetime.strptime(event.group(1), "%d-%m-%Y").date()
            range_to = datetime.strptime(event.group(2), "%d-%m-%Y").date()
            exact = event_api_url_v1(range_from, range_to)
        except ValueError:
            return None
        if exact == url:
            return _MAX_EVENT_BYTES, "text/csv", True
        return None
    holiday = re.fullmatch(
        re.escape(NSE_HOLIDAY_MASTER_URL) + r"\?type=trading&year=(\d{4})",
        url,
    )
    if holiday is not None:
        year = int(holiday.group(1))
        if 2000 <= year <= 2100 and nse_holiday_master_url_v1(year) == url:
            return _MAX_SCHEDULE_BYTES, "application/json", False
        return None
    timing = re.fullmatch(
        re.escape(UPSTOX_TIMINGS_URL) + r"/(\d{4}-\d{2}-\d{2})",
        url,
    )
    if timing is not None:
        try:
            trade_date = date.fromisoformat(timing.group(1))
        except ValueError:
            return None
        if upstox_market_timings_url_v1(trade_date) == url:
            return _MAX_SCHEDULE_BYTES, "application/json", False
    return None


def _observation_structure_is_exact_v1(
    value: OfficialHttpObservationV1,
) -> bool:
    try:
        spec = _observation_required_spec_v1(value.request_url)
        if spec is None:
            return False
        maximum_bytes, media_type, disposition_required = spec
        headers = value.headers
        if (
            value.response_url != value.request_url
            or value.status != 200
            or type(headers) is not tuple
            or len(headers) > len(_PROVENANCE_HEADERS)
            or len({name.casefold() for name, _ in headers}) != len(headers)
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not str
                or type(item[1]) is not str
                or item[0].casefold() not in _PROVENANCE_HEADERS
                or not item[0].isascii()
                or not item[1].isascii()
                or any(
                    character != "\t" and not " " <= character <= "~"
                    for character in item[1]
                )
                for item in headers
            )
            or sum(
                len(name.encode("latin-1")) + len(header.encode("latin-1"))
                for name, header in headers
            )
            > _MAX_PROVENANCE_HEADER_BYTES
            or type(value.body) is not bytes
            or not 1 <= len(value.body) <= maximum_bytes
            or not _is_utc(value.known_at)
            or not 2000 <= value.known_at.year <= 2100
            or type(value.cookie_count) is not int
            or type(value.cookie_aggregate_bytes) is not int
            or not 0 <= value.cookie_count <= _MAX_COOKIES
            or not 0 <= value.cookie_aggregate_bytes <= _MAX_COOKIE_BYTES
        ):
            return False
        value.body.decode("utf-8")
        by_name = {name.casefold(): header for name, header in headers}
        if _closed_content_type_source_encoding_v1(
            by_name.get("content-type"), media_type
        ) != "UTF-8" or (
            "content-encoding" in by_name and by_name["content-encoding"] != "identity"
        ):
            return False
        content_length = by_name.get("content-length")
        if content_length is not None and (
            not content_length.isdigit() or int(content_length) != len(value.body)
        ):
            return False
        disposition = by_name.get("content-disposition")
        if disposition_required and (
            disposition is None or _CONTENT_DISPOSITION.fullmatch(disposition) is None
        ):
            return False
        return value.observation_identity_sha256 == _identity(value.identity_value())
    except (
        AttributeError,
        TypeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        ValueError,
    ):
        return False


def _official_observation_is_exact_v1(value: object) -> bool:
    return (
        type(value) is OfficialHttpObservationV1
        and _official_observation_registered(value, value.observation_identity_sha256)
        and _observation_structure_is_exact_v1(value)
    )


def _observation_set_binding(
    value: CurrentEvidenceObservationsV1,
) -> tuple[tuple[int, str], ...]:
    return tuple((id(item), item.observation_identity_sha256) for item in value.all)


def _observation_set_is_exact_v1(value: object) -> bool:
    try:
        if type(value) is not CurrentEvidenceObservationsV1:
            return False
        observations = value.all
        return (
            5 <= len(observations) <= _MAX_OBSERVATIONS
            and len(value.nse_holiday_masters) in (1, 2)
            and len({item.observation_identity_sha256 for item in observations})
            == len(observations)
            and all(_official_observation_is_exact_v1(item) for item in observations)
            and _observation_set_registered(value, _observation_set_binding(value))
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _calendar_observation_set_binding(
    value: CurrentCalendarEvidenceObservationsV1,
) -> tuple[tuple[int, str], ...]:
    return tuple((id(item), item.observation_identity_sha256) for item in value.all)


def _calendar_observation_set_is_exact_v1(value: object) -> bool:
    try:
        if type(value) is not CurrentCalendarEvidenceObservationsV1:
            return False
        observations = value.all
        return (
            2 <= len(observations) <= _MAX_SHARED_CALENDAR_OBSERVATIONS
            and len(value.nse_holiday_masters) in (1, 2)
            and len({item.observation_identity_sha256 for item in observations})
            == len(observations)
            and all(_official_observation_is_exact_v1(item) for item in observations)
            and _observation_set_registered(
                value, _calendar_observation_set_binding(value)
            )
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _calendar_observations_from_combined(
    observations: CurrentEvidenceObservationsV1,
) -> CurrentCalendarEvidenceObservationsV1:
    if not _observation_set_is_exact_v1(observations):
        raise ValueError("invalid composed schedule input")
    return _mint_calendar_observation_set(
        (
            observations.upstox_current_year_holidays,
            *observations.nse_holiday_masters,
            *observations.upstox_prior_year_timings,
        ),
        holiday_master_count=len(observations.nse_holiday_masters),
    )


def _calendar_bundle_binding(
    value: CurrentCalendarEvidenceBundleV1,
) -> tuple[object, ...]:
    return (
        id(value.observations),
        hashlib.sha256(value.source_manifest_bytes).hexdigest(),
        value.source_manifest_sha256,
        id(value.schedule),
        value.schedule_evidence_sha256,
        value.runtime_code_identity_sha256,
    )


def _calendar_bundle_components_are_exact_v1(
    value: CurrentCalendarEvidenceBundleV1,
) -> bool:
    try:
        if not _calendar_observation_set_is_exact_v1(value.observations):
            return False
        manifest_bytes, schedule = _compose_calendar_schedule_v1(
            observations=value.observations,
            coverage_from=value.schedule.covered_from,
            coverage_to=value.schedule.covered_to,
            as_of=value.schedule.as_of,
        )
        return (
            manifest_bytes == value.source_manifest_bytes
            and hashlib.sha256(manifest_bytes).hexdigest()
            == value.source_manifest_sha256
            and schedule == value.schedule
            and schedule_digest(schedule) == value.schedule_evidence_sha256
            and value.runtime_code_identity_sha256
            == current_evidence_acquisition_runtime_code_identity_v1()
        )
    except (
        AttributeError,
        CurrentEvidenceAcquisitionError,
        TypeError,
        ValueError,
    ):
        return False


def validate_current_calendar_evidence_bundle_v1(value: object) -> bool:
    """Revalidate one exact private calendar bundle before downstream adoption."""
    try:
        return (
            type(value) is CurrentCalendarEvidenceBundleV1
            and _evidence_bundle_registered(value, _calendar_bundle_binding(value))
            and _calendar_bundle_components_are_exact_v1(value)
        )
    except (AttributeError, TypeError, ValueError):
        return False


def _bundle_binding(value: CurrentSprint14EvidenceBundleV1) -> tuple[object, ...]:
    return (
        id(value.observations),
        hashlib.sha256(value.source_manifest_bytes).hexdigest(),
        value.source_manifest_sha256,
        id(value.schedule),
        value.schedule_evidence_sha256,
        value.runtime_code_identity_sha256,
        id(value.industry_input),
        hashlib.sha256(value.industry_artifact).hexdigest(),
        id(value.event_input),
        hashlib.sha256(value.event_artifact).hexdigest(),
    )


def _bundle_components_are_exact_v1(
    value: CurrentSprint14EvidenceBundleV1,
) -> bool:
    try:
        if not _observation_set_is_exact_v1(value.observations):
            return False
        manifest_bytes, schedule = compose_current_nse_schedule_v1(
            observations=value.observations,
            coverage_from=value.schedule.covered_from,
            coverage_to=value.schedule.covered_to,
            as_of=value.schedule.as_of,
        )
        event_from = value.schedule.covered_to - timedelta(days=1)
        event_media = {
            name.casefold(): header
            for name, header in value.observations.event_csv.headers
        }.get("content-type")
        parsed_industry = parse_current_industry_artifact_v1(
            value.industry_input, value.industry_artifact
        )
        parsed_event = parse_current_event_notice_artifact_v1(
            value.event_input, value.event_artifact
        )
        return (
            manifest_bytes == value.source_manifest_bytes
            and hashlib.sha256(manifest_bytes).hexdigest()
            == value.source_manifest_sha256
            and schedule == value.schedule
            and schedule_digest(schedule) == value.schedule_evidence_sha256
            and value.runtime_code_identity_sha256
            == current_evidence_acquisition_runtime_code_identity_v1()
            and value.industry_artifact is value.observations.industry.body
            and value.industry_input.artifact_sha256
            == value.observations.industry.body_sha256
            and type(parsed_industry) is not CurrentIndustryClassificationFailureV1
            and value.event_artifact is value.observations.event_csv.body
            and value.event_input.artifact_identity_sha256
            == value.observations.event_csv.body_sha256
            and value.event_input.source_filename
            == _event_filename_from_observation(
                value.observations.event_csv,
                event_from,
                value.schedule.covered_to,
            )
            and value.event_input.acquisition_method == "BOUNDED_OFFICIAL_FETCH"
            and value.event_input.licence_policy_identity
            == EVENT_LICENCE_POLICY_IDENTITY
            and value.event_input.source_encoding
            == _closed_content_type_source_encoding_v1(event_media, "text/csv")
            and value.event_input.source_has_bom
            is value.event_artifact.startswith(b"\xef\xbb\xbf")
            and type(parsed_event) is not CurrentEventNoticeFailureV1
        )
    except (
        AttributeError,
        CurrentEvidenceAcquisitionError,
        TypeError,
        ValueError,
    ):
        return False


def validate_current_sprint14_evidence_bundle_v1(value: object) -> bool:
    """Revalidate one exact acquisition-minted bundle before downstream adoption."""
    try:
        return (
            type(value) is CurrentSprint14EvidenceBundleV1
            and _evidence_bundle_registered(value, _bundle_binding(value))
            and _bundle_components_are_exact_v1(value)
        )
    except (AttributeError, TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class _UpstoxNseException:
    trade_date: date
    holiday_type: str
    closed: bool
    open_at: datetime | None
    close_at: datetime | None


@dataclass(frozen=True, slots=True)
class _UpstoxDateTiming:
    trade_date: date
    open_at: datetime | None
    close_at: datetime | None


@dataclass(frozen=True, slots=True)
class _NseClosure:
    trade_date: date
    description: str


class _NoRedirectHandler(SameOriginAuthorizationRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


class BoundedOfficialHttpSessionV1:
    """Cookie-preserving, no-redirect urllib session with fixed resource bounds."""

    def __init__(self) -> None:
        self._cookies = CookieJar()
        redirect = _NoRedirectHandler()
        opener = build_opener(redirect, HTTPCookieProcessor(self._cookies))
        self._transport = UrllibHttpTransport(
            timeout_seconds=_TIMEOUT_SECONDS,
            max_body_bytes=_MAX_BODY_BYTES,
            opener=opener.open,
        )

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        response = self._transport.get(url, headers)
        cookie_bytes = sum(
            len(cookie.name.encode("utf-8"))
            + len((cookie.value or "").encode("utf-8"))
            + len(cookie.domain.encode("utf-8"))
            + len(cookie.path.encode("utf-8"))
            for cookie in self._cookies
        )
        if len(self._cookies) > _MAX_COOKIES or cookie_bytes > _MAX_COOKIE_BYTES:
            self._cookies.clear()
            raise CurrentEvidenceAcquisitionError("COOKIE_BOUNDS_EXCEEDED")
        return response


def event_api_url_v1(range_from: date, range_to: date) -> str:
    """Return the sole admitted unfiltered Equity 1D CSV endpoint URL."""
    if (
        type(range_from) is not date
        or type(range_to) is not date
        or not 2000 <= range_from.year <= range_to.year <= 2100
        or range_to - range_from != timedelta(days=1)
    ):
        raise ValueError("invalid event 1D range")
    return (
        f"{NSE_ANNOUNCEMENTS_API_URL}?index=equities"
        f"&from_date={range_from.strftime('%d-%m-%Y')}"
        f"&to_date={range_to.strftime('%d-%m-%Y')}&csv=true"
    )


def nse_holiday_master_url_v1(year: int) -> str:
    if type(year) is not int or not 2000 <= year <= 2100:
        raise ValueError("invalid holiday-master year")
    return f"{NSE_HOLIDAY_MASTER_URL}?type=trading&year={year}"


def upstox_market_timings_url_v1(trade_date: date) -> str:
    if type(trade_date) is not date or not 2000 <= trade_date.year <= 2100:
        raise ValueError("invalid market-timings date")
    return f"{UPSTOX_TIMINGS_URL}/{trade_date.isoformat()}"


def acquire_current_calendar_evidence_v1(
    *,
    transport: HttpTransport,
    clock: TrustedClockV1,
    coverage_from: date,
    as_of: datetime,
) -> CurrentCalendarEvidenceBundleV1:
    """Acquire only the bounded calendar sources admitted by the common policy."""
    if type(coverage_from) is not date or not _is_utc(as_of):
        raise ValueError("invalid current calendar evidence request")
    coverage_to = _local_ist_date(as_of)
    if (
        not callable(getattr(transport, "get", None))
        or not callable(clock)
        or coverage_from > coverage_to
        or not 2000 <= coverage_from.year <= coverage_to.year <= 2100
        or (coverage_to - coverage_from).days + 1 > _MAX_CURRENT_CALENDAR_COVERAGE_DAYS
    ):
        raise ValueError("invalid current calendar evidence request")
    years = tuple(range(coverage_from.year, coverage_to.year + 1))
    prior_year_dates = tuple(
        coverage_from + timedelta(days=offset)
        for offset in range((coverage_to - coverage_from).days + 1)
        if (coverage_from + timedelta(days=offset)).year != coverage_to.year
    )
    if len(years) not in (1, 2) or 1 + len(years) + len(prior_year_dates) > (
        _MAX_CALENDAR_OBSERVATIONS
    ):
        raise ValueError("invalid current calendar evidence request")
    _require_calendar_acquisition_time(
        _trusted_clock_instant(clock), as_of=as_of, coverage_to=coverage_to
    )
    specs: list[tuple[str, dict[str, str], int, str, bool]] = [
        (
            UPSTOX_HOLIDAYS_URL,
            {"Accept": "application/json"},
            _MAX_SCHEDULE_BYTES,
            "application/json",
            False,
        )
    ]
    specs.extend(
        (
            nse_holiday_master_url_v1(year),
            {
                "Accept": "application/json",
                "Referer": (
                    "https://www.nseindia.com/resources/exchange-communication-holidays"
                ),
            },
            _MAX_SCHEDULE_BYTES,
            "application/json",
            False,
        )
        for year in years
    )
    specs.extend(
        (
            upstox_market_timings_url_v1(trade_date),
            {"Accept": "application/json"},
            _MAX_SCHEDULE_BYTES,
            "application/json",
            False,
        )
        for trade_date in prior_year_dates
    )
    observed: list[OfficialHttpObservationV1] = []
    for index, (
        url,
        headers,
        maximum_bytes,
        content_type,
        require_disposition,
    ) in enumerate(specs):
        _require_calendar_acquisition_time(
            _trusted_clock_instant(clock), as_of=as_of, coverage_to=coverage_to
        )
        observation = _fetch_exact(
            transport,
            clock,
            url=url,
            headers=headers,
            maximum_bytes=maximum_bytes,
            content_type=content_type,
            require_content_disposition=require_disposition,
        )
        _require_calendar_acquisition_time(
            observation.known_at, as_of=as_of, coverage_to=coverage_to
        )
        if index == 0:
            _parse_upstox(observation.body, expected_year=coverage_to.year)
        elif index <= len(years):
            _parse_nse_closures(observation.body, expected_year=years[index - 1])
        else:
            _parse_upstox_timing(
                observation.body,
                expected_date=prior_year_dates[index - len(years) - 1],
            )
        observed.append(observation)
    composition_known_at = _trusted_clock_instant(clock)
    _require_calendar_acquisition_time(
        composition_known_at, as_of=as_of, coverage_to=coverage_to
    )
    observations = _mint_calendar_observation_set(
        tuple(observed), holiday_master_count=len(years)
    )
    manifest_bytes, schedule = _compose_calendar_schedule_v1(
        observations=observations,
        coverage_from=coverage_from,
        coverage_to=coverage_to,
        as_of=composition_known_at,
    )
    return _mint_calendar_bundle(
        observations=observations,
        source_manifest_bytes=manifest_bytes,
        schedule=schedule,
    )


def _require_calendar_acquisition_time(
    known_at: datetime, *, as_of: datetime, coverage_to: date
) -> None:
    if _local_ist_date(known_at) != coverage_to:
        raise CurrentEvidenceAcquisitionError("ACQUISITION_DATE_ROLLOVER")
    if known_at > as_of:
        raise CurrentEvidenceAcquisitionError("ACQUISITION_CUTOFF_EXCEEDED")


def acquire_current_sprint14_evidence_v1(
    *,
    transport: HttpTransport,
    clock: TrustedClockV1,
    coverage_from: date,
    as_of: datetime,
) -> CurrentSprint14EvidenceBundleV1:
    """Fetch only the bounded current licensed capability; never fall back."""
    if type(coverage_from) is not date:
        raise ValueError("invalid current evidence acquisition request")
    coverage_from = coverage_from.replace(day=1)
    coverage_to = _local_ist_date(as_of) if _is_utc(as_of) else None
    transport_get = getattr(transport, "get", None)
    if (
        not callable(transport_get)
        or not callable(clock)
        or type(coverage_from) is not date
        or coverage_to is None
        or coverage_from > coverage_to
        or not 2000 <= coverage_from.year <= coverage_to.year <= 2100
        or (coverage_to - coverage_from).days + 1 > _MAX_COVERAGE_DAYS
    ):
        raise ValueError("invalid current evidence acquisition request")
    years = tuple(range(coverage_from.year, coverage_to.year + 1))
    if len(years) not in (1, 2):
        raise ValueError("invalid current evidence acquisition request")
    prior_year_dates = tuple(
        coverage_from + timedelta(days=offset)
        for offset in range((coverage_to - coverage_from).days + 1)
        if (coverage_from + timedelta(days=offset)).year != coverage_to.year
    )

    event_from = coverage_to - timedelta(days=1)
    event_url = event_api_url_v1(event_from, coverage_to)
    specs: list[tuple[str, dict[str, str], int, str, bool]] = [
        (
            INDUSTRY_URL,
            {"Accept": "text/csv"},
            _MAX_INDUSTRY_BYTES,
            "text/csv",
            False,
        ),
        (
            NSE_ANNOUNCEMENTS_PAGE_URL,
            {"Accept": "text/html"},
            _MAX_PAGE_BYTES,
            "text/html",
            False,
        ),
        (
            event_url,
            {
                "Accept": "text/csv",
                "Referer": NSE_ANNOUNCEMENTS_PAGE_URL,
            },
            _MAX_EVENT_BYTES,
            "text/csv",
            True,
        ),
        (
            UPSTOX_HOLIDAYS_URL,
            {"Accept": "application/json"},
            _MAX_SCHEDULE_BYTES,
            "application/json",
            False,
        ),
    ]
    specs.extend(
        (
            nse_holiday_master_url_v1(year),
            {
                "Accept": "application/json",
                "Referer": (
                    "https://www.nseindia.com/resources/exchange-communication-holidays"
                ),
            },
            _MAX_SCHEDULE_BYTES,
            "application/json",
            False,
        )
        for year in years
    )
    specs.extend(
        (
            upstox_market_timings_url_v1(trade_date),
            {"Accept": "application/json"},
            _MAX_SCHEDULE_BYTES,
            "application/json",
            False,
        )
        for trade_date in prior_year_dates
    )
    if len(specs) > _MAX_OBSERVATIONS:
        raise ValueError("invalid current evidence acquisition request")
    observed = tuple(
        _fetch_exact(
            transport,
            clock,
            url=url,
            headers=headers,
            maximum_bytes=maximum_bytes,
            content_type=content_type,
            require_content_disposition=require_disposition,
        )
        for (
            url,
            headers,
            maximum_bytes,
            content_type,
            require_disposition,
        ) in specs
    )
    observations = _mint_observation_set(observed, holiday_master_count=len(years))
    industry_input = _industry_input(observations.industry)
    parsed_industry = parse_current_industry_artifact_v1(
        industry_input, observations.industry.body
    )
    if type(parsed_industry) is CurrentIndustryClassificationFailureV1:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")

    event_source_has_bom = observations.event_csv.body.startswith(b"\xef\xbb\xbf")
    event_filename = _event_filename_from_observation(
        observations.event_csv, event_from, coverage_to
    )
    event_input = CurrentEventNoticeInputV1(
        schema_identity_sha256=EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        source_url=NSE_ANNOUNCEMENTS_PAGE_URL,
        source_segment="Equity",
        source_window="1D",
        source_filename=event_filename,
        artifact_identity_sha256=observations.event_csv.body_sha256,
        licence_policy_identity=EVENT_LICENCE_POLICY_IDENTITY,
        source_encoding="UTF-8",
        acquisition_method="BOUNDED_OFFICIAL_FETCH",
        source_has_bom=event_source_has_bom,
    )
    parsed_event = parse_current_event_notice_artifact_v1(
        event_input, observations.event_csv.body
    )
    if type(parsed_event) is CurrentEventNoticeFailureV1:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")

    composition_known_at = _trusted_clock_instant(clock)
    if (
        composition_known_at > as_of
        or _local_ist_date(composition_known_at) != coverage_to
        or any(item.known_at > composition_known_at for item in observations)
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    manifest_bytes, schedule = compose_current_nse_schedule_v1(
        observations=observations,
        coverage_from=coverage_from,
        coverage_to=coverage_to,
        as_of=composition_known_at,
    )
    return _mint_bundle(
        observations=observations,
        source_manifest_bytes=manifest_bytes,
        schedule=schedule,
        industry_input=industry_input,
        event_input=event_input,
    )


def acquire_current_sprint14_evidence_default_v1(
    *,
    coverage_from: date,
    as_of: datetime,
    clock: TrustedClockV1,
) -> CurrentSprint14EvidenceBundleV1:
    """Run the sole current licensed live edge with private bounded cookies."""
    return acquire_current_sprint14_evidence_v1(
        transport=BoundedOfficialHttpSessionV1(),
        clock=clock,
        coverage_from=coverage_from,
        as_of=as_of,
    )


def _compose_calendar_schedule_v1(  # noqa: C901
    *,
    observations: CurrentCalendarEvidenceObservationsV1,
    coverage_from: date,
    coverage_to: date,
    as_of: datetime,
) -> tuple[bytes, ExpectedSessionSchedule]:
    """Replay the one shared bounded calendar composition policy."""
    if (
        not _calendar_observation_set_is_exact_v1(observations)
        or type(coverage_from) is not date
        or type(coverage_to) is not date
        or coverage_from > coverage_to
        or not 2000 <= coverage_from.year <= coverage_to.year <= 2100
        or (coverage_to - coverage_from).days + 1 > _MAX_COVERAGE_DAYS
        or not _is_utc(as_of)
        or not 2000 <= as_of.year <= 2100
        or coverage_to != _local_ist_date(as_of)
        or any(item.known_at > as_of for item in observations)
    ):
        raise ValueError("invalid composed schedule input")
    years = tuple(range(coverage_from.year, coverage_to.year + 1))
    prior_year_dates = tuple(
        coverage_from + timedelta(days=offset)
        for offset in range((coverage_to - coverage_from).days + 1)
        if (coverage_from + timedelta(days=offset)).year != coverage_to.year
    )
    if (
        len(years) not in (1, 2)
        or observations.upstox_current_year_holidays.request_url != UPSTOX_HOLIDAYS_URL
        or tuple(item.request_url for item in observations.nse_holiday_masters)
        != tuple(nse_holiday_master_url_v1(year) for year in years)
        or tuple(item.request_url for item in observations.upstox_prior_year_timings)
        != tuple(upstox_market_timings_url_v1(day) for day in prior_year_dates)
    ):
        raise ValueError("invalid composed schedule input")

    upstox = _parse_upstox(
        observations.upstox_current_year_holidays.body,
        expected_year=coverage_to.year,
    )
    closures = tuple(
        closure
        for year, observation in zip(
            years, observations.nse_holiday_masters, strict=True
        )
        for closure in _parse_nse_closures(observation.body, expected_year=year)
    )
    if len({item.trade_date for item in closures}) != len(closures):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    prior_timings = tuple(
        _parse_upstox_timing(observation.body, expected_date=trade_date)
        for trade_date, observation in zip(
            prior_year_dates,
            observations.upstox_prior_year_timings,
            strict=True,
        )
    )
    upstox_by_date = {item.trade_date: item for item in upstox}
    closure_by_date = {item.trade_date: item for item in closures}
    timing_by_date = {item.trade_date: item for item in prior_timings}
    sessions: list[ScheduleSession] = []
    closed_dates: list[ScheduleClosure] = []
    current = coverage_from
    while current <= coverage_to:
        official_closure = closure_by_date.get(current)
        if current.year != coverage_to.year:
            timing = timing_by_date.get(current)
            if timing is None:
                raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
            if timing.open_at is not None and timing.close_at is not None:
                if official_closure is not None:
                    raise CurrentEvidenceAcquisitionError("SOURCE_CONFLICT")
                _require_regular_explicit_opening(
                    current, timing.open_at, timing.close_at
                )
                sessions.append(
                    ScheduleSession(
                        current,
                        timing.open_at,
                        timing.close_at,
                        "REGULAR",
                    )
                )
            elif official_closure is not None:
                closed_dates.append(_closure(current, official_closure))
            elif current.weekday() >= 5:
                closed_dates.append(_closure(current, None))
            else:
                raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
            current += timedelta(days=1)
            continue

        provider = upstox_by_date.get(current)
        if (
            provider is not None
            and provider.open_at is not None
            and provider.close_at is not None
        ):
            if official_closure is not None:
                raise CurrentEvidenceAcquisitionError("SOURCE_CONFLICT")
            if provider.holiday_type == "SPECIAL_TIMING":
                raise CurrentEvidenceAcquisitionError("SPECIAL_SESSION_UNCORROBORATED")
            _require_regular_explicit_opening(
                current, provider.open_at, provider.close_at
            )
            sessions.append(
                ScheduleSession(
                    current,
                    provider.open_at,
                    provider.close_at,
                    "REGULAR",
                )
            )
        elif provider is not None and provider.closed:
            if current.weekday() < 5 and official_closure is None:
                raise CurrentEvidenceAcquisitionError("SOURCE_CONFLICT")
            closed_dates.append(_closure(current, official_closure))
        elif official_closure is not None:
            closed_dates.append(_closure(current, official_closure))
        elif current.weekday() >= 5:
            closed_dates.append(_closure(current, None))
        else:
            open_at, close_at = _regular_opening(current)
            sessions.append(ScheduleSession(current, open_at, close_at, "REGULAR"))
        current += timedelta(days=1)

    manifest = {
        "as_of": _instant(as_of),
        "composition_policy": {
            "fail_closed_on": [
                "HTTP_OR_PARSE_FAILURE",
                "SOURCE_CONFLICT",
                "DUPLICATE_DATE_OR_NSE_OPEN",
                "EMPTY_OR_INCOMPLETE_SOURCE",
                "NSE_BOTH_OPEN_AND_CLOSED",
                "INVALID_OR_NONLOCAL_PROVIDER_TIMES",
                "UNRECOGNIZED_HOLIDAY_TYPE",
                "SPECIAL_SESSION_UNCORROBORATED",
            ],
            "precedence": [
                "UPSTOX_NSE_EXPLICIT",
                "NSE_CM_CLOSURE",
                "WEEKEND_POLICY",
                "REGULAR_WEEKDAY_POLICY_CURRENT_YEAR_ONLY",
            ],
            "version": SCHEDULE_COMPOSITION_VERSION,
        },
        "contract_version": "nse-upstox-composed-calendar-source@v1",
        "coverage_from": coverage_from.isoformat(),
        "coverage_to": coverage_to.isoformat(),
        "runtime_code_identity_sha256": (
            current_evidence_acquisition_runtime_code_identity_v1()
        ),
        "inputs": {
            "nse_holiday_masters": [
                _observation_manifest(item, "CM")
                for item in observations.nse_holiday_masters
            ],
            "upstox_current_year_market_holidays": _observation_manifest(
                observations.upstox_current_year_holidays
            ),
            "upstox_prior_year_market_timings": [
                _observation_manifest(item)
                for item in observations.upstox_prior_year_timings
            ],
        },
        "official_nse_regular_session_policy": {
            "applies_to": "NSE_EQUITY_CAPITAL_MARKET",
            "regular_close_local": "15:30",
            "regular_open_local": "09:15",
            "regular_weekdays": [
                "MONDAY",
                "TUESDAY",
                "WEDNESDAY",
                "THURSDAY",
                "FRIDAY",
            ],
            "source_url": (
                "https://www.nseindia.com/resources/exchange-communication-holidays"
            ),
            "weekend_days": ["SATURDAY", "SUNDAY"],
        },
        "timezone": "Asia/Kolkata",
    }
    manifest_bytes = _canonical(manifest)
    if len(manifest_bytes) > _MAX_SCHEDULE_BYTES:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    release = "composed-calendar@v1=" + hashlib.sha256(manifest_bytes).hexdigest()
    schedule = ExpectedSessionSchedule(
        SCHEDULE_SCHEMA_VERSION_V3,
        SCHEDULE_SOURCE,
        release,
        as_of,
        "Asia/Kolkata",
        coverage_from,
        coverage_to,
        tuple(sessions),
        tuple(closed_dates),
    )
    return manifest_bytes, schedule


def compose_current_nse_schedule_v1(
    *,
    observations: CurrentEvidenceObservationsV1,
    coverage_from: date,
    coverage_to: date,
    as_of: datetime,
) -> tuple[bytes, ExpectedSessionSchedule]:
    """Replay legacy combined inputs through the shared calendar policy."""
    if (
        not _observation_set_is_exact_v1(observations)
        or type(coverage_to) is not date
        or not 2000 <= coverage_to.year <= 2100
        or not _is_utc(as_of)
        or any(item.known_at > as_of for item in observations)
        or observations.industry.request_url != INDUSTRY_URL
        or observations.announcements_page.request_url != NSE_ANNOUNCEMENTS_PAGE_URL
        or observations.event_csv.request_url
        != event_api_url_v1(coverage_to - timedelta(days=1), coverage_to)
    ):
        raise ValueError("invalid composed schedule input")
    return _compose_calendar_schedule_v1(
        observations=_calendar_observations_from_combined(observations),
        coverage_from=coverage_from,
        coverage_to=coverage_to,
        as_of=as_of,
    )


def _closed_content_type_source_encoding_v1(
    value: object, required_media_type: object
) -> str | None:
    """Return UTF-8 for the closed grammar with ASCII case-insensitive tokens."""
    if (
        type(value) is not str
        or not value.isascii()
        or type(required_media_type) is not str
        or required_media_type not in {"text/csv", "text/html", "application/json"}
    ):
        return None
    normalized = value.lower()
    if normalized in {
        required_media_type,
        f"{required_media_type}; charset=utf-8",
    }:
        return "UTF-8"
    return None


def _fetch_exact(  # noqa: C901
    transport: HttpTransport,
    clock: TrustedClockV1,
    *,
    url: str,
    headers: dict[str, str],
    maximum_bytes: int,
    content_type: str,
    require_content_disposition: bool,
) -> OfficialHttpObservationV1:
    if (
        not _safe_url(url)
        or type(headers) is not dict
        or not all(
            type(name) is str and type(value) is str for name, value in headers.items()
        )
        or type(maximum_bytes) is not int
        or not 1 <= maximum_bytes <= _MAX_BODY_BYTES
        or type(content_type) is not str
        or content_type not in {"text/csv", "text/html", "application/json"}
        or type(require_content_disposition) is not bool
    ):
        raise ValueError("invalid bounded fetch specification")
    request_headers = dict(headers)
    request_headers["User-Agent"] = DEFAULT_USER_AGENT
    try:
        response = transport.get(url, request_headers)
    except CurrentEvidenceAcquisitionError:
        raise
    except HttpResponseBodyTooLarge:
        raise CurrentEvidenceAcquisitionError("RESPONSE_TOO_LARGE") from None
    except (HttpTransportError, HttpResponseHeadersInvalid):
        raise CurrentEvidenceAcquisitionError("HTTP_FAILURE") from None
    if type(response) is not HttpResponse or response.status_code != 200:
        raise CurrentEvidenceAcquisitionError("HTTP_FAILURE")
    if response.request_url != url or response.response_url != url:
        raise CurrentEvidenceAcquisitionError("SOURCE_MISMATCH")
    if type(response.body) is not bytes or not 1 <= len(response.body) <= maximum_bytes:
        raise CurrentEvidenceAcquisitionError("RESPONSE_TOO_LARGE")
    try:
        response.body.decode("utf-8")
    except UnicodeDecodeError:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED") from None
    raw_headers = response.headers.items()
    for name in _PROVENANCE_HEADERS:
        if sum(1 for raw_name, _ in raw_headers if raw_name.casefold() == name) > 1:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    response_content_type = response.headers.get_single("Content-Type")
    if (
        _closed_content_type_source_encoding_v1(response_content_type, content_type)
        is None
    ):
        raise CurrentEvidenceAcquisitionError("CONTENT_TYPE_MISMATCH")
    content_encoding = response.headers.get_single("Content-Encoding")
    if content_encoding is not None and content_encoding != "identity":
        raise CurrentEvidenceAcquisitionError("CONTENT_TYPE_MISMATCH")
    content_length = response.headers.get_single("Content-Length")
    if content_length is not None:
        try:
            valid_length = (
                content_length.isascii()
                and content_length.isdigit()
                and int(content_length) == len(response.body)
            )
        except ValueError:
            valid_length = False
        if not valid_length:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    disposition = response.headers.get_single("Content-Disposition")
    if require_content_disposition and disposition is None:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    cookie_headers = tuple(
        (name, value) for name, value in raw_headers if name.casefold() == "set-cookie"
    )
    cookie_bytes = sum(
        len(name.encode("latin-1")) + len(value.encode("latin-1"))
        for name, value in cookie_headers
    )
    if len(cookie_headers) > _MAX_COOKIES or cookie_bytes > _MAX_COOKIE_BYTES:
        raise CurrentEvidenceAcquisitionError("COOKIE_BOUNDS_EXCEEDED")
    provenance_headers = tuple(
        (name, value)
        for name, value in raw_headers
        if name.casefold() in _PROVENANCE_HEADERS
    )
    return _mint_observation(
        request_url=url,
        response_url=url,
        status=response.status_code,
        headers=provenance_headers,
        body=response.body,
        known_at=_trusted_clock_instant(clock),
        cookie_count=len(cookie_headers),
        cookie_aggregate_bytes=cookie_bytes,
    )


def _trusted_clock_instant(clock: TrustedClockV1) -> datetime:
    try:
        value = clock()
        if not _is_utc(value) or not 2000 <= value.year <= 2100:
            raise ValueError
        return value
    except (OSError, OverflowError, RecursionError, ValueError):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED") from None


def _local_ist_date(value: datetime) -> date:
    try:
        return value.astimezone(_IST).date()
    except (OSError, OverflowError, RecursionError, ValueError):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED") from None


def _event_filename_from_observation(
    observation: OfficialHttpObservationV1,
    requested_from: date,
    requested_to: date,
) -> str:
    values = tuple(
        value
        for name, value in observation.headers
        if name.casefold() == "content-disposition"
    )
    if len(values) != 1:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    match = _CONTENT_DISPOSITION.fullmatch(values[0].strip())
    if match is None:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    filename = match.group(1) or match.group(2)
    parsed_range = _event_filename_range(filename)
    if parsed_range != (requested_from, requested_to):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    return filename


def _event_filename_range(value: object) -> tuple[date, date] | None:
    if type(value) is not str or not _safe_ascii(value, 128):
        return None
    match = _EVENT_FILENAME.fullmatch(value)
    if match is None:
        return None
    try:
        range_from = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        range_to = date(int(match.group(6)), int(match.group(5)), int(match.group(4)))
    except ValueError:
        return None
    return (
        (range_from, range_to) if range_to - range_from == timedelta(days=1) else None
    )


def _industry_input(
    observation: OfficialHttpObservationV1,
) -> CurrentIndustryClassificationInputV1:
    value: dict[str, object] = {
        "contract_version": "current-supplied-cohort-industry-classification@v1",
        "schema_identity_sha256": CLASSIFICATION_SCHEMA_IDENTITY_SHA256,
        "source_url": INDUSTRY_URL,
        "source_authority": "NSE_INDICES",
        "source_domain": "nsearchives.nseindia.com",
        "acquisition_method": INDUSTRY_ACQUISITION_METHOD,
        "artifact_byte_count": observation.body_byte_count,
        "artifact_sha256": observation.body_sha256,
        "artifact_revision": f"sha256:{observation.body_sha256}",
        "classification_tier": "INDUSTRY",
        "publisher_published_at": None,
        "publisher_effective_from": None,
        "publisher_effective_through": None,
        "publisher_revision": None,
        "licence_policy_identity_sha256": (INDUSTRY_LICENCE_POLICY_IDENTITY_SHA256),
    }
    return CurrentIndustryClassificationInputV1(value)


def _parse_upstox(  # noqa: C901
    raw: bytes, *, expected_year: int
) -> tuple[_UpstoxNseException, ...]:
    value = _json_object(raw)
    if set(value) != {"status", "data"} or value.get("status") != "success":
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    raw_data = value.get("data")
    if type(raw_data) is not list:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    data = cast(list[object], raw_data)
    if not 1 <= len(data) <= _MAX_NSE_HOLIDAY_ROWS:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    results: list[_UpstoxNseException] = []
    seen: set[date] = set()
    has_nse_semantics = False
    for raw_row in data:
        if not _string_object_dict(raw_row) or set(raw_row) != {
            "date",
            "description",
            "holiday_type",
            "closed_exchanges",
            "open_exchanges",
        }:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        trade_date = _iso_date(raw_row["date"])
        holiday_type = raw_row["holiday_type"]
        description = raw_row["description"]
        raw_closed_exchanges = raw_row["closed_exchanges"]
        raw_open_exchanges = raw_row["open_exchanges"]
        if (
            trade_date is None
            or trade_date.year != expected_year
            or trade_date in seen
            or type(holiday_type) is not str
            or holiday_type not in _RECOGNIZED_HOLIDAY_TYPES
            or type(description) is not str
            or not _safe_ascii(description, 256)
            or type(raw_closed_exchanges) is not list
            or type(raw_open_exchanges) is not list
        ):
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        closed_items = cast(list[object], raw_closed_exchanges)
        open_items = cast(list[object], raw_open_exchanges)
        if len(closed_items) > 32 or len(open_items) > 32:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        if not all(
            type(item) is str and _safe_ascii(item, 32) for item in closed_items
        ):
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        closed_exchanges = cast(list[str], closed_items)
        if len(set(closed_exchanges)) != len(closed_exchanges):
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        nse_open: list[dict[str, object]] = []
        seen_open_exchanges: set[str] = set()
        for item in open_items:
            if not _string_object_dict(item) or set(item) != {
                "exchange",
                "start_time",
                "end_time",
            }:
                raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
            exchange = item["exchange"]
            if (
                type(exchange) is not str
                or not _safe_ascii(exchange, 32)
                or exchange in seen_open_exchanges
                or type(item["start_time"]) is not int
                or type(item["end_time"]) is not int
            ):
                raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
            seen_open_exchanges.add(exchange)
            if exchange == "NSE":
                nse_open.append(item)
        if len(nse_open) > 1:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        closed = "NSE" in closed_exchanges
        if closed and nse_open:
            raise CurrentEvidenceAcquisitionError("SOURCE_CONFLICT")
        open_at: datetime | None = None
        close_at: datetime | None = None
        if nse_open:
            open_at = _epoch_millis(nse_open[0]["start_time"], trade_date)
            close_at = _epoch_millis(nse_open[0]["end_time"], trade_date)
            if open_at is None or close_at is None or open_at >= close_at:
                raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        has_nse_semantics = has_nse_semantics or closed or bool(nse_open)
        results.append(
            _UpstoxNseException(
                trade_date,
                holiday_type,
                closed,
                open_at,
                close_at,
            )
        )
        seen.add(trade_date)
    if not has_nse_semantics:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    return tuple(results)


def _parse_upstox_timing(raw: bytes, *, expected_date: date) -> _UpstoxDateTiming:
    value = _json_object(raw)
    raw_data = value.get("data")
    if (
        set(value) != {"status", "data"}
        or value.get("status") != "success"
        or type(raw_data) is not list
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    data = cast(list[object], raw_data)
    if len(data) > 32:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    nse_row: dict[str, object] | None = None
    seen: set[str] = set()
    for raw_row in data:
        if not _string_object_dict(raw_row) or set(raw_row) != {
            "exchange",
            "start_time",
            "end_time",
        }:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        exchange = raw_row["exchange"]
        if (
            type(exchange) is not str
            or not _safe_ascii(exchange, 32)
            or exchange in seen
            or type(raw_row["start_time"]) is not int
            or type(raw_row["end_time"]) is not int
        ):
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        seen.add(exchange)
        if exchange == "NSE":
            nse_row = raw_row
    if nse_row is None:
        return _UpstoxDateTiming(expected_date, None, None)
    open_at = _epoch_millis(nse_row["start_time"], expected_date)
    close_at = _epoch_millis(nse_row["end_time"], expected_date)
    if open_at is None or close_at is None or open_at >= close_at:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    return _UpstoxDateTiming(expected_date, open_at, close_at)


def _parse_nse_closures(raw: bytes, *, expected_year: int) -> tuple[_NseClosure, ...]:
    value = _json_object(raw)
    if tuple(sorted(value)) != _NSE_HOLIDAY_SEGMENTS:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    for segment, raw_segment_rows in value.items():
        if type(raw_segment_rows) is not list:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        segment_rows = cast(list[object], raw_segment_rows)
        if len(segment_rows) > _MAX_NSE_HOLIDAY_ROWS or (
            segment == "CM" and not segment_rows
        ):
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    rows = cast(list[object], value["CM"])
    results: list[_NseClosure] = []
    seen_dates: set[date] = set()
    for raw_row in rows:
        if not _string_object_dict(raw_row) or set(raw_row) != {
            "tradingDate",
            "weekDay",
            "description",
            "morning_session",
            "evening_session",
        }:
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        trade_date = _english_date(raw_row["tradingDate"])
        description = raw_row["description"]
        week_day = raw_row["weekDay"]
        if (
            trade_date is None
            or trade_date.year != expected_year
            or trade_date in seen_dates
            or type(description) is not str
            or not _safe_ascii(description, 128)
            or type(week_day) is not str
            or week_day != _WEEKDAYS[trade_date.weekday()]
            or raw_row["morning_session"] is not None
            or raw_row["evening_session"] is not None
        ):
            raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
        results.append(_NseClosure(trade_date, description))
        seen_dates.add(trade_date)
    return tuple(results)


def _regular_opening(trade_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(trade_date, _REGULAR_OPEN, _IST).astimezone(UTC),
        datetime.combine(trade_date, _REGULAR_CLOSE, _IST).astimezone(UTC),
    )


def _require_regular_explicit_opening(
    trade_date: date, open_at: datetime, close_at: datetime
) -> None:
    if (open_at, close_at) != _regular_opening(trade_date):
        raise CurrentEvidenceAcquisitionError("SPECIAL_SESSION_UNCORROBORATED")


def _closure(trade_date: date, official: _NseClosure | None) -> ScheduleClosure:
    if official is not None:
        return ScheduleClosure(
            trade_date,
            f"NSE_CM_HOLIDAY:{official.description}",
        )
    day = "SATURDAY" if trade_date.weekday() == 5 else "SUNDAY"
    return ScheduleClosure(trade_date, f"COMPOSED_WEEKEND_POLICY:{day}")


def _observation_manifest(
    observation: OfficialHttpObservationV1, segment: str | None = None
) -> dict[str, object]:
    headers = {name.lower(): value for name, value in observation.headers}
    result: dict[str, object] = {
        "content_encoding": headers.get("content-encoding", "identity"),
        "content_type": headers.get("content-type"),
        "decoded_byte_length": observation.body_byte_count,
        "cookie_aggregate_bytes": observation.cookie_aggregate_bytes,
        "cookie_count": observation.cookie_count,
        "decoded_sha256": observation.body_sha256,
        "etag": headers.get("etag"),
        "http_date": headers.get("date"),
        "known_at": _instant(observation.known_at),
        "last_modified": headers.get("last-modified"),
        "observation_identity_sha256": observation.observation_identity_sha256,
        "redirected": False,
        "request_url": observation.request_url,
        "response_headers": [list(item) for item in observation.headers],
        "response_url": observation.response_url,
        "status": observation.status,
    }
    if segment is not None:
        result["segment"] = segment
    return result


def _json_object(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_SCHEDULE_BYTES:
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_number,
            parse_float=_reject_json_number,
            parse_int=_bounded_json_int,
        )
        _validate_json_tree(value)
    except (
        OSError,
        OverflowError,
        RecursionError,
        UnicodeDecodeError,
        ValueError,
    ):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED") from None
    if not _string_object_dict(value):
        raise CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    return value


def _unique_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_json_number(_: str) -> object:
    raise ValueError


def _bounded_json_int(value: str) -> int:
    if len(value.lstrip("-")) > 19:
        raise ValueError
    return int(value)


def _validate_json_tree(value: object) -> None:
    nodes = 0
    stack: list[tuple[object, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            raise ValueError
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            if not all(type(key) is str for key in mapping):
                raise ValueError
            stack.extend((item, depth + 1) for item in mapping.values())
        elif type(current) is list:
            items = cast(list[object], current)
            if len(items) > _MAX_JSON_ARRAY_ITEMS:
                raise ValueError
            stack.extend((item, depth + 1) for item in items)
        elif type(current) not in (str, int, bool, type(None)):
            raise ValueError


def _string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if type(value) is not dict:
        return False
    mapping = cast(dict[object, object], value)
    return all(type(key) is str for key in mapping)


def _iso_date(value: object) -> date | None:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _english_date(value: object) -> date | None:
    if type(value) is not str:
        return None
    match = _NSE_DATE.fullmatch(value)
    if match is None:
        return None
    month = _MONTHS.get(match.group(2))
    if month is None:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def _epoch_millis(value: object, expected_date: date) -> datetime | None:
    if (
        type(value) is not int
        or type(expected_date) is not date
        or value < 0
        or value % 60_000
    ):
        return None
    try:
        parsed = datetime.fromtimestamp(value // 1000, UTC) + timedelta(
            milliseconds=value % 1000
        )
        return parsed if parsed.astimezone(_IST).date() == expected_date else None
    except (OSError, OverflowError, ValueError):
        return None


def _safe_ascii(value: str, maximum: int) -> bool:
    return (
        1 <= len(value.encode("utf-8")) <= maximum
        and value.isascii()
        and all(character.isprintable() for character in value)
    )


def _safe_url(value: object) -> TypeGuard[str]:
    return (
        type(value) is str
        and _safe_ascii(value, _MAX_URL_BYTES)
        and value.startswith("https://")
        and "\\" not in value
        and "#" not in value
    )


def _is_utc(value: object) -> TypeGuard[datetime]:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _instant(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _base64_encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _base64_decode(value: object, *, maximum_bytes: int) -> bytes:
    if type(value) is not str or type(maximum_bytes) is not int:
        raise ValueError("invalid current calendar evidence")
    maximum_encoded = 4 * ((maximum_bytes + 2) // 3)
    if not 1 <= len(value) <= maximum_encoded or not value.isascii():
        raise ValueError("invalid current calendar evidence")
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except ValueError:
        raise ValueError("invalid current calendar evidence") from None
    if not 1 <= len(decoded) <= maximum_bytes:
        raise ValueError("invalid current calendar evidence")
    return decoded


def _calendar_observation_value(
    observation: OfficialHttpObservationV1,
) -> dict[str, object]:
    return {
        "body_b64": _base64_encode(observation.body),
        "cookie_aggregate_bytes": observation.cookie_aggregate_bytes,
        "cookie_count": observation.cookie_count,
        "headers": [list(item) for item in observation.headers],
        "known_at": _instant(observation.known_at),
        "observation_identity_sha256": observation.observation_identity_sha256,
        "request_url": observation.request_url,
        "response_url": observation.response_url,
        "status": observation.status,
    }


def _parse_calendar_instant(value: object) -> datetime:
    if type(value) is not str or not _safe_ascii(value, 32):
        raise ValueError("invalid current calendar evidence")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid current calendar evidence") from None
    if not _is_utc(result) or _instant(result) != value:
        raise ValueError("invalid current calendar evidence")
    return result


def _parse_calendar_observation(
    value: object,
) -> OfficialHttpObservationV1:
    if not _string_object_dict(value) or set(value) != {
        "body_b64",
        "cookie_aggregate_bytes",
        "cookie_count",
        "headers",
        "known_at",
        "observation_identity_sha256",
        "request_url",
        "response_url",
        "status",
    }:
        raise ValueError("invalid current calendar evidence")
    request_url = value["request_url"]
    spec = _observation_required_spec_v1(request_url)
    if (
        spec is None
        or request_url
        in {
            INDUSTRY_URL,
            NSE_ANNOUNCEMENTS_PAGE_URL,
        }
        or (
            type(request_url) is str
            and request_url.startswith(NSE_ANNOUNCEMENTS_API_URL)
        )
    ):
        raise ValueError("invalid current calendar evidence")
    headers_value = cast(list[list[object]], value["headers"])
    if (
        type(headers_value) is not list
        or len(headers_value) > len(_PROVENANCE_HEADERS)
        or any(
            type(item) is not list
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) is not str
            for item in headers_value
        )
    ):
        raise ValueError("invalid current calendar evidence")
    observation = _mint_observation(
        request_url=cast(str, request_url),
        response_url=cast(str, value["response_url"]),
        status=cast(int, value["status"]),
        headers=tuple(
            (cast(str, item[0]), cast(str, item[1])) for item in headers_value
        ),
        body=_base64_decode(value["body_b64"], maximum_bytes=spec[0]),
        known_at=_parse_calendar_instant(value["known_at"]),
        cookie_count=cast(int, value["cookie_count"]),
        cookie_aggregate_bytes=cast(int, value["cookie_aggregate_bytes"]),
    )
    if observation.observation_identity_sha256 != value["observation_identity_sha256"]:
        raise ValueError("invalid current calendar evidence")
    return observation


def parse_current_calendar_evidence_v1(
    raw: object,
) -> CurrentCalendarEvidenceBundleV1:
    """Re-admit only exact bounded private calendar evidence bytes."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_CALENDAR_EVIDENCE_BYTES:
        raise ValueError("invalid current calendar evidence")
    try:
        parsed: object = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_number,
            parse_int=_bounded_json_int,
        )
        _validate_json_tree(parsed)
        if (
            not _string_object_dict(parsed)
            or set(parsed)
            != {
                "observations",
                "runtime_code_identity_sha256",
                "schedule_b64",
                "schedule_evidence_sha256",
                "schema_version",
                "source_manifest_b64",
                "source_manifest_sha256",
            }
            or parsed["schema_version"] != 1
        ):
            raise ValueError
        schedule_bytes = _base64_decode(
            parsed["schedule_b64"], maximum_bytes=_MAX_SCHEDULE_BYTES
        )
        schedule = parse_canonical_schedule_bytes(schedule_bytes)
        observations_value = cast(list[object], parsed["observations"])
        if (
            type(observations_value) is not list
            or not 2 <= len(observations_value) <= _MAX_CALENDAR_OBSERVATIONS
        ):
            raise ValueError
        observations_raw = tuple(
            _parse_calendar_observation(item) for item in observations_value
        )
        years = tuple(range(schedule.covered_from.year, schedule.covered_to.year + 1))
        prior_year_dates = tuple(
            schedule.covered_from + timedelta(days=offset)
            for offset in range((schedule.covered_to - schedule.covered_from).days + 1)
            if (schedule.covered_from + timedelta(days=offset)).year
            != schedule.covered_to.year
        )
        expected_urls = (
            UPSTOX_HOLIDAYS_URL,
            *(nse_holiday_master_url_v1(year) for year in years),
            *(upstox_market_timings_url_v1(day) for day in prior_year_dates),
        )
        if (
            len(years) not in (1, 2)
            or tuple(item.request_url for item in observations_raw) != expected_urls
        ):
            raise ValueError
        observations = _mint_calendar_observation_set(
            observations_raw, holiday_master_count=len(years)
        )
        source_manifest_bytes = _base64_decode(
            parsed["source_manifest_b64"], maximum_bytes=_MAX_SCHEDULE_BYTES
        )
        if (
            type(parsed["source_manifest_sha256"]) is not str
            or hashlib.sha256(source_manifest_bytes).hexdigest()
            != parsed["source_manifest_sha256"]
            or type(parsed["schedule_evidence_sha256"]) is not str
            or schedule_digest(schedule) != parsed["schedule_evidence_sha256"]
            or type(parsed["runtime_code_identity_sha256"]) is not str
        ):
            raise ValueError
        result = _mint_calendar_bundle(
            observations=observations,
            source_manifest_bytes=source_manifest_bytes,
            schedule=schedule,
        )
        if (
            result.runtime_code_identity_sha256
            != parsed["runtime_code_identity_sha256"]
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError
        return result
    except (
        CurrentEvidenceAcquisitionError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ):
        raise ValueError("invalid current calendar evidence") from None


def _identity(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def current_evidence_acquisition_runtime_code_identity_v1() -> str:
    """Verify exact acquisition source, dependencies, and manifest bytes at rest."""
    prefix = "src/swing_trading_ai_assistant/market_data/"
    manifest_path = prefix + "current_evidence_acquisition_runtime_identity_manifest.py"
    modules = {
        prefix + "current_evidence_acquisition.py": __name__,
        prefix + "current_event_notice.py": (
            "swing_trading_ai_assistant.market_data.current_event_notice"
        ),
        prefix + "current_industry_classification.py": (
            "swing_trading_ai_assistant.market_data.current_industry_classification"
        ),
        prefix + "http.py": "swing_trading_ai_assistant.market_data.http",
        prefix + "schedule_evidence.py": (
            "swing_trading_ai_assistant.market_data.schedule_evidence"
        ),
        prefix + "runtime_source_verifier.py": (
            "swing_trading_ai_assistant.market_data.runtime_source_verifier"
        ),
        manifest_path: (
            "swing_trading_ai_assistant.market_data."
            "current_evidence_acquisition_runtime_identity_manifest"
        ),
    }
    package_root = Path(__file__).resolve().parents[1]
    try:
        expected = CURRENT_EVIDENCE_ACQUISITION_RUNTIME_SOURCE_SHA256_V1
        expected_paths = tuple(path for path in modules if path != manifest_path)
        if tuple(expected) != expected_paths:
            raise ValueError
        sources: list[dict[str, str]] = []
        for relative_path in sorted(modules):
            observed = runtime_source_sha256(
                modules[relative_path], package_root, relative_path
            )
            if relative_path != manifest_path and observed != expected[relative_path]:
                raise ValueError
            sources.append({"relative_path": relative_path, "source_sha256": observed})
        return _identity(
            {
                "runtime_manifest_version": "current-evidence-acquisition-runtime@v1",
                "modules": sources,
            }
        )
    except (OSError, ValueError):
        raise ValueError("acquisition runtime code identity unavailable") from None
