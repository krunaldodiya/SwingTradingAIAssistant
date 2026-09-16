"""Admission-capability contracts for the current Industry archive reader."""

from __future__ import annotations

import copy
import json
import os
import pickle
from dataclasses import asdict, replace
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.current_industry_archive_reader as reader_module
from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
    CurrentIndustryArchiveReferenceV1,
    current_industry_projection_is_admitted_v1,
    read_current_industry_archive_exact_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    AdmittedCurrentRawContextV1,
    admitted_current_raw_context_binding_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


def _forged() -> AdmittedCurrentIndustryProjectionV1:
    candidate = object.__new__(AdmittedCurrentIndustryProjectionV1)
    object.__setattr__(candidate, "_seal", object())
    return candidate


def test_industry_projection_cannot_be_constructed_copied_or_serialized() -> None:
    with pytest.raises(TypeError, match="constructor unavailable"):
        AdmittedCurrentIndustryProjectionV1()  # type: ignore[call-arg]
    candidate = _forged()
    assert current_industry_projection_is_admitted_v1(candidate) is False
    assert repr(candidate) == "AdmittedCurrentIndustryProjectionV1()"
    assert set(asdict(candidate)) == {"_seal"}
    with pytest.raises(AttributeError):
        object.__setattr__(candidate, "rows", ())
    for operation in (
        lambda: copy.copy(candidate),
        lambda: copy.deepcopy(candidate),
        lambda: pickle.dumps(candidate),
        lambda: replace(candidate),
        lambda: json.dumps(candidate),
    ):
        with pytest.raises(TypeError):
            operation()


def test_raw_capability_cannot_be_constructed_or_serialized() -> None:
    with pytest.raises(TypeError, match="constructor unavailable"):
        AdmittedCurrentRawContextV1()  # type: ignore[call-arg]
    candidate = object.__new__(AdmittedCurrentRawContextV1)
    object.__setattr__(candidate, "_seal", object())
    assert repr(candidate) == "AdmittedCurrentRawContextV1()"
    assert set(asdict(candidate)) == {"_seal"}
    with pytest.raises(AttributeError):
        object.__setattr__(candidate, "projection", object())
    for operation in (
        lambda: copy.copy(candidate),
        lambda: copy.deepcopy(candidate),
        lambda: pickle.dumps(candidate),
        lambda: replace(candidate),
        lambda: json.dumps(candidate),
        lambda: admitted_current_raw_context_binding_v1(candidate),
    ):
        with pytest.raises((TypeError, ValueError)):
            operation()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ValueError("injected value fault"), "injected value fault"),
        (TypeError("injected type fault"), "injected type fault"),
        (RuntimeError("reader implementation fault"), "reader implementation fault"),
    ],
)
def test_reader_propagates_injected_stable_object_helper_faults(
    monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    def unexpected(*_: object) -> tuple[bytes, object] | None:
        raise error

    monkeypatch.setattr(reader_module, "_read_stable_private_object", unexpected)
    with pytest.raises(type(error), match=message):
        reader_module._read(  # pyright: ignore[reportPrivateUsage]
            0, "snapshot-any.json", 1
        )


def test_reader_closes_real_oversized_archive_object_as_malformed(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "archive"
    archive.mkdir(mode=0o700)
    object_path = archive / "snapshot.json"
    object_path.write_bytes(b"malformed")
    object_path.chmod(0o400)
    directory = os.open(archive, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        with pytest.raises(reader_module._IndustryLocalRefusal) as raised:  # pyright: ignore[reportPrivateUsage]
            reader_module._read(  # pyright: ignore[reportPrivateUsage]
                directory, object_path.name, 1
            )
    finally:
        os.close(directory)
    assert (raised.value.state, raised.value.reason) == (
        "MALFORMED_EVIDENCE",
        "CLASSIFICATION_ARCHIVE_MALFORMED",
    )


def test_reader_refuses_a_caller_forged_raw_authority_before_archive_io(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    acquired = StorageRootLease.try_acquire_private_empty(tmp_path)
    assert acquired.lease is not None
    try:
        with pytest.raises(ValueError, match="not admitted"):
            read_current_industry_archive_exact_v1(
                CurrentIndustryArchiveReferenceV1(
                    "current-industry-archive-reference@v1", "a" * 64, "b" * 64
                ),
                storage_root=tmp_path,
                lease=acquired.lease,
                raw=object(),  # type: ignore[arg-type]
            )
    finally:
        acquired.lease.close()
