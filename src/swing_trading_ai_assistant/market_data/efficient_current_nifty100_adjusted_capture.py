"""Official Nifty 100 selection policy over one BharatStock V2 capture request."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast
from urllib.request import HTTPRedirectHandler, build_opener

from . import bharatstock_capture as capture_store
from .bharatstock import BharatStockClient, BharatStockInstrument
from .bharatstock_capture import (
    CaptureRequestV2,
    CaptureResultV2,
    capture_bharatstock_v2,
    validate_capture_revision_v2,
)
from .http import (
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransportError,
    UrllibHttpTransport,
)

CONTRACT_VERSION_V2 = "current-nifty100-bharatstock-capture@v2"
NIFTY_50_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"
NIFTY_NEXT_50_URL = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
)
NIFTY_100_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
_MAX_SOURCE_BYTES = 1_000_000
_MAX_RETAINED_SELECTION_BYTES = 3 * 4 * ((_MAX_SOURCE_BYTES + 2) // 3) + 64 * 1024


@dataclass(frozen=True, slots=True)
class SourceResponseV2:
    request_url: str
    response_url: str
    status: int
    body: bytes
    retrieved_at: datetime


class SourceFetcherV2(Protocol):
    def get(self, url: str) -> SourceResponseV2: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        return None


class OfficialSourceFetcherV2:
    """Bounded official-list fetcher; redirects are never accepted as identity."""

    def __init__(self) -> None:
        self._transport = UrllibHttpTransport(
            max_body_bytes=_MAX_SOURCE_BYTES,
            opener=build_opener(_NoRedirect()).open,
        )

    def get(self, url: str) -> SourceResponseV2:
        if url not in (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL):
            raise ValueError("official selection URL unsupported")
        try:
            response = self._transport.get(url, {"Accept": "text/csv"})
        except (
            HttpTransportError,
            HttpResponseBodyTooLarge,
            HttpResponseHeadersInvalid,
        ) as error:
            raise OSError("official selection unavailable") from error
        if response.request_url is None or response.response_url is None:
            raise OSError("official selection URL evidence missing")
        return SourceResponseV2(
            request_url=response.request_url,
            response_url=response.response_url,
            status=response.status_code,
            body=response.body,
            retrieved_at=datetime.now(UTC),
        )


@dataclass(frozen=True, slots=True)
class OfficialSelectionV2:
    members: tuple[BharatStockInstrument, ...]
    selection_identity_sha256: str
    source_identity_sha256: str
    retrieved_at: datetime
    source_bytes: tuple[bytes, bytes, bytes]
    source_urls: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class CurrentNifty100ResultV2:
    code: str
    revision_identity_sha256: str | None
    requested_members: int
    observed_members: int
    insufficient_members: int
    unattempted_members: int
    shared_failure: str | None
    reason: str | None


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _parse_source(body: bytes, count: int) -> tuple[BharatStockInstrument, ...] | None:
    if not body or len(body) > _MAX_SOURCE_BYTES:
        return None
    expected = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    try:
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig"), newline=""))
        header = next(reader, None)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        return None
    if (
        header is None
        or len(header) != len(expected)
        or set(header) != expected
        or len(rows) != count
        or any(len(row) != len(header) for row in rows)
    ):
        return None
    positions = {column: header.index(column) for column in expected}
    try:
        members = tuple(
            BharatStockInstrument(
                isin=row[positions["ISIN Code"]],
                exchange="NSE",
                symbol=row[positions["Symbol"]],
            )
            for row in rows
            if row[positions["Series"]] == "EQ"
        )
    except ValueError:
        return None
    if (
        len(members) != count
        or len({member.isin for member in members}) != count
        or len({member.symbol for member in members}) != count
    ):
        return None
    return members


def admit_current_nifty100_selection_v2(
    fetcher: SourceFetcherV2,
) -> OfficialSelectionV2 | None:
    """Fetch and cross-check Nifty 50, Next 50, and Nifty 100 official lists."""

    try:
        responses = tuple(
            fetcher.get(url) for url in (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL)
        )
    except OSError:
        return None
    if any(
        type(response) is not SourceResponseV2
        or response.request_url != url
        or response.response_url != url
        or response.status != 200
        or response.retrieved_at.tzinfo is None
        or len(response.body) > _MAX_SOURCE_BYTES
        for url, response in zip(
            (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL),
            responses,
            strict=True,
        )
    ):
        return None
    first, second, witness = (
        _parse_source(response.body, count)
        for response, count in zip(responses, (50, 50, 100), strict=True)
    )
    if first is None or second is None or witness is None:
        return None
    if {member.isin for member in first} & {member.isin for member in second}:
        return None
    joined = first + second
    if {(member.isin, member.symbol) for member in joined} != {
        (member.isin, member.symbol) for member in witness
    }:
        return None
    source_identity = _digest(
        [
            {
                "url": response.request_url,
                "sha256": hashlib.sha256(response.body).hexdigest(),
            }
            for response in responses
        ]
    )
    selection_identity = capture_store.selection_identity_v2(joined)
    return OfficialSelectionV2(
        members=joined,
        selection_identity_sha256=selection_identity,
        source_identity_sha256=source_identity,
        retrieved_at=max(response.retrieved_at for response in responses),
        source_bytes=(responses[0].body, responses[1].body, responses[2].body),
        source_urls=(NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL),
    )


def _retain_selection_v2(
    selection: OfficialSelectionV2, request: CaptureRequestV2, root: Path
) -> bool:
    """Persist immutable source evidence and an exact request-to-evidence binding."""

    lease = capture_store._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        return False
    evidence = (
        _canonical(
            {
                "members": [
                    {
                        "exchange": member.exchange,
                        "isin": member.isin,
                        "symbol": member.symbol,
                    }
                    for member in selection.members
                ],
                "selection_identity_sha256": selection.selection_identity_sha256,
                "source_bytes_b64": [
                    base64.b64encode(body).decode("ascii")
                    for body in selection.source_bytes
                ],
                "source_identity_sha256": selection.source_identity_sha256,
                "retrieved_at": selection.retrieved_at.astimezone(UTC).isoformat(),
                "source_urls": list(selection.source_urls),
            }
        )
        + b"\n"
    )
    binding = (
        _canonical(
            {
                "request_identity_sha256": request.request_identity_sha256,
                "source_identity_sha256": selection.source_identity_sha256,
            }
        )
        + b"\n"
    )
    try:
        with lease.root_operation(root) as operation:
            namespace = capture_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                operation, operation.descriptor, "nifty100-selection-v2", create=True
            )
            try:
                sources = capture_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, namespace, "sources", create=True
                )
                requests = capture_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, namespace, "requests", create=True
                )
                try:
                    capture_store._publish(  # pyright: ignore[reportPrivateUsage]
                        sources, f"{selection.source_identity_sha256}.json", evidence
                    )
                    capture_store._publish(  # pyright: ignore[reportPrivateUsage]
                        requests, f"{request.request_identity_sha256}.json", binding
                    )
                    return True
                finally:
                    requests.close()
                    sources.close()
            finally:
                namespace.close()
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    finally:
        lease.close()


def _parse_retained_selection(
    raw: bytes, binding_source_identity: str, request: CaptureRequestV2
) -> OfficialSelectionV2 | None:
    """Revalidate retained source bytes against the exact capture selection."""
    value = json.loads(raw)
    if type(value) is not dict:
        return None
    retained = cast(dict[str, object], value)
    if set(retained) != {
        "members",
        "retrieved_at",
        "selection_identity_sha256",
        "source_bytes_b64",
        "source_identity_sha256",
        "source_urls",
    }:
        return None
    retained_members = retained["members"]
    retained_urls = retained["source_urls"]
    retained_source_bytes = retained["source_bytes_b64"]
    retrieved_at_value = retained["retrieved_at"]
    selection_identity_value = retained["selection_identity_sha256"]
    source_identity_value = retained["source_identity_sha256"]
    if (
        type(retained_members) is not list
        or len(cast(list[object], retained_members)) != 100
        or type(retained_urls) is not list
        or tuple(cast(list[object], retained_urls))
        != (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL)
        or type(retained_source_bytes) is not list
        or len(cast(list[object], retained_source_bytes)) != 3
        or type(retrieved_at_value) is not str
        or type(selection_identity_value) is not str
        or type(source_identity_value) is not str
    ):
        return None
    member_values = cast(list[object], retained_members)
    for item in member_values:
        if type(item) is not dict or set(cast(dict[object, object], item)) != {
            "exchange",
            "isin",
            "symbol",
        }:
            return None
        member = cast(dict[str, object], item)
        if any(type(member[field]) is not str for field in member):
            return None
    source_byte_values = cast(list[object], retained_source_bytes)
    if any(type(item) is not str for item in source_byte_values):
        return None
    members = tuple(
        BharatStockInstrument(item["isin"], item["exchange"], item["symbol"])
        for item in cast(list[dict[str, str]], member_values)
    )
    source_bodies = [
        base64.b64decode(item.encode("ascii"), validate=True)
        for item in cast(list[str], source_byte_values)
    ]
    source_bytes = (source_bodies[0], source_bodies[1], source_bodies[2])
    first, second, witness = (
        _parse_source(body, count)
        for body, count in zip(source_bytes, (50, 50, 100), strict=True)
    )
    retrieved_at = datetime.fromisoformat(retrieved_at_value)
    if (
        first is None
        or second is None
        or witness is None
        or {member.isin for member in first} & {member.isin for member in second}
        or first + second != members
        or {(member.isin, member.symbol) for member in members}
        != {(member.isin, member.symbol) for member in witness}
        or capture_store.selection_identity_v2(members)
        != request.selection_identity_sha256
        or selection_identity_value != request.selection_identity_sha256
        or source_identity_value != binding_source_identity
        or retrieved_at > request.decision_cutoff
        or source_identity_value
        != _digest(
            [
                {"url": url, "sha256": hashlib.sha256(body).hexdigest()}
                for url, body in zip(
                    (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL),
                    source_bytes,
                    strict=True,
                )
            ]
        )
    ):
        return None
    return OfficialSelectionV2(
        members,
        request.selection_identity_sha256,
        source_identity_value,
        retrieved_at,
        source_bytes,
        (NIFTY_50_URL, NIFTY_NEXT_50_URL, NIFTY_100_URL),
    )


def _read_retained_selection_v2(
    root: Path, request: CaptureRequestV2
) -> OfficialSelectionV2 | None:
    lease = capture_store._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        return None
    try:
        with lease.read_operation(root) as operation:
            namespace = capture_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                operation, operation.descriptor, "nifty100-selection-v2", create=False
            )
            try:
                requests = capture_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, namespace, "requests", create=False
                )
                try:
                    binding_value = json.loads(
                        capture_store._read_exact(  # pyright: ignore[reportPrivateUsage]
                            requests, f"{request.request_identity_sha256}.json", 512
                        )
                    )
                finally:
                    requests.close()
                if type(binding_value) is not dict:
                    return None
                binding = cast(dict[str, object], binding_value)
                binding_source_identity = binding.get("source_identity_sha256")
                if (
                    set(binding)
                    != {
                        "request_identity_sha256",
                        "source_identity_sha256",
                    }
                    or binding.get("request_identity_sha256")
                    != request.request_identity_sha256
                    or type(binding_source_identity) is not str
                    or len(binding_source_identity) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in binding_source_identity
                    )
                ):
                    return None
                sources = capture_store._open_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, namespace, "sources", create=False
                )
                try:
                    raw = capture_store._read_exact(  # pyright: ignore[reportPrivateUsage]
                        sources,
                        f"{binding_source_identity}.json",
                        _MAX_RETAINED_SELECTION_BYTES,
                    )
                finally:
                    sources.close()
            finally:
                namespace.close()
        return _parse_retained_selection(raw, binding_source_identity, request)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    finally:
        lease.close()


def project_current_nifty100_capture_v2(
    selection: OfficialSelectionV2, capture: CaptureResultV2
) -> CurrentNifty100ResultV2:
    """Redact members publicly while retaining the exact V2 revision privately."""

    if capture.revision is None:
        return CurrentNifty100ResultV2(
            code="INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
            revision_identity_sha256=None,
            requested_members=100,
            observed_members=0,
            insufficient_members=0,
            unattempted_members=100,
            shared_failure=None,
            reason=capture.reason,
        )
    revision = capture.revision
    try:
        validate_capture_revision_v2(revision)
    except ValueError:
        return CurrentNifty100ResultV2(
            "INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
            None,
            100,
            0,
            100,
            0,
            None,
            "CAPTURE_REVISION_INVALID",
        )
    if (
        len(selection.members) != 100
        or revision.request.members != selection.members
        or revision.request.selection_identity_sha256
        != selection.selection_identity_sha256
    ):
        return CurrentNifty100ResultV2(
            "INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
            None,
            100,
            0,
            0,
            0,
            None,
            "SELECTION_CONFLICT",
        )
    observed = sum(member.evidence_state == "OBSERVED" for member in revision.members)
    insufficient = sum(
        member.evidence_state == "INSUFFICIENT_EVIDENCE" for member in revision.members
    )
    unattempted = sum(
        member.evidence_state == "NOT_ATTEMPTED" for member in revision.members
    )
    complete = observed == 100 and revision.shared_failure is None
    return CurrentNifty100ResultV2(
        "COMPLETE_CURRENT_NIFTY100_CAPTURE"
        if complete
        else "INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
        revision.revision_identity_sha256,
        100,
        observed,
        insufficient,
        unattempted,
        revision.shared_failure,
        None
        if complete
        else (revision.shared_failure or "MEMBER_EVIDENCE_INSUFFICIENT"),
    )


def capture_current_nifty100_v2(
    request: CaptureRequestV2,
    *,
    selection_root: Path,
    capture_root: Path,
    schedule_root: Path,
    fetcher: SourceFetcherV2 | None = None,
    client: BharatStockClient | None = None,
) -> CurrentNifty100ResultV2:
    """Validate official selection before the serial, provider-neutral V2 capture."""

    selection = _read_retained_selection_v2(selection_root, request)
    if selection is None:
        selection = admit_current_nifty100_selection_v2(
            fetcher or OfficialSourceFetcherV2()
        )
        if selection is None:
            return CurrentNifty100ResultV2(
                "INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
                None,
                100,
                0,
                0,
                100,
                None,
                "CONSTITUENT_SOURCE_INVALID",
            )
        if (
            request.members != selection.members
            or request.selection_identity_sha256 != selection.selection_identity_sha256
            or selection.retrieved_at > request.decision_cutoff
        ):
            return CurrentNifty100ResultV2(
                "INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
                None,
                100,
                0,
                0,
                100,
                None,
                "CONSTITUENT_SOURCE_CONFLICT",
            )
        if not _retain_selection_v2(selection, request, selection_root):
            return CurrentNifty100ResultV2(
                "INCOMPLETE_CURRENT_NIFTY100_CAPTURE",
                None,
                100,
                0,
                0,
                100,
                None,
                "SELECTION_RETENTION_FAILED",
            )
    return project_current_nifty100_capture_v2(
        selection,
        capture_bharatstock_v2(request, capture_root, schedule_root, client=client),
    )


def serialize_capture_result_v2(result: CurrentNifty100ResultV2) -> dict[str, object]:
    """Return the public redacted capture binding and exact private revision handle."""

    return {
        "code": result.code,
        "contract_version": CONTRACT_VERSION_V2,
        "insufficient_members": result.insufficient_members,
        "observed_members": result.observed_members,
        "reason": result.reason,
        "requested_members": result.requested_members,
        "revision_identity_sha256": result.revision_identity_sha256,
        "shared_failure": result.shared_failure,
        "unattempted_members": result.unattempted_members,
    }
