"""Retained Industry bytes remain authoritative through final CLI projection."""

from __future__ import annotations

from datetime import timedelta

import pytest
from test_agent_cohort_fatal_boundaries import _assert_fatal_output, _run_cli
from test_agent_cohort_integration import _run_api, _setup

from swing_trading_ai_assistant.market_data import agent_cohort_context as api
from swing_trading_ai_assistant.market_data import (
    current_industry_classification as archive,
)


def _damage(root, pattern, substitute=False):
    target = next((root / ".current-industry-classification-v1").glob(pattern))
    mode = target.stat().st_mode & 0o777
    original = target.read_bytes()
    inode = target.stat().st_ino
    if substitute:
        replacement = target.with_suffix(".substitute")
        replacement.write_bytes(original)
        replacement.chmod(mode)
        replacement.replace(target)
        assert target.stat().st_ino != inode
        assert target.read_bytes() == original
    else:
        target.chmod(0o600)
        target.write_bytes(b"corrupt")
        target.chmod(mode)


@pytest.mark.parametrize(
    "pattern", ["raw-*.csv", "snapshot-*.json", "retained-*.json", "completion-*.json"]
)
@pytest.mark.parametrize("substitute", [False, True])
def test_retained_industry_damage_after_archive_is_fatal(
    tmp_path, monkeypatch, capsys, pattern, substitute
):
    root, path, members, kwargs, _, _ = _setup(tmp_path, monkeypatch)
    original = archive.FileCurrentIndustryArchiveV1.archive_exact

    def damage(self, *args, **options):
        value = original(self, *args, **options)
        assert type(value) is archive.RetainedCurrentIndustrySnapshotV1
        _damage(root, pattern, substitute)
        return value

    monkeypatch.setattr(archive.FileCurrentIndustryArchiveV1, "archive_exact", damage)
    _assert_fatal_output(capsys, _run_cli(monkeypatch, root, path, members, kwargs))


def test_retained_industry_corruption_wins_over_deadline(tmp_path, monkeypatch, capsys):
    root, path, members, kwargs, _, _ = _setup(tmp_path, monkeypatch)
    original = archive.FileCurrentIndustryArchiveV1.archive_exact

    def damage(self, *args, **options):
        value = original(self, *args, **options)
        _damage(root, "raw-*.csv")
        kwargs["clock"].__self__.value += timedelta(minutes=30)
        return value

    monkeypatch.setattr(archive.FileCurrentIndustryArchiveV1, "archive_exact", damage)
    _assert_fatal_output(capsys, _run_cli(monkeypatch, root, path, members, kwargs))


@pytest.mark.parametrize("boundary", ["reducer", "projection"])
def test_retained_industry_corruption_after_projection_is_fatal(
    tmp_path, monkeypatch, capsys, boundary
):
    root, path, members, kwargs, _, _ = _setup(tmp_path, monkeypatch)
    module = api.industry if boundary == "reducer" else api
    name = (
        "reduce_current_industry_participation_v4"
        if boundary == "reducer"
        else "_industry"
    )
    original = getattr(module, name)

    def damage(*args, **options):
        value = original(*args, **options)
        _damage(root, "snapshot-*.json")
        return value

    monkeypatch.setattr(module, name, damage)
    _assert_fatal_output(capsys, _run_cli(monkeypatch, root, path, members, kwargs))


@pytest.mark.parametrize("expired", [False, True])
def test_unchanged_industry_binding_preserves_exact_files_and_knowledge(
    tmp_path, monkeypatch, expired
):
    root, path, members, kwargs, _, _ = _setup(tmp_path, monkeypatch)
    original = archive.FileCurrentIndustryArchiveV1.archive_exact
    observations = []

    def observe(self, *args, **options):
        value = original(self, *args, **options)
        files = {
            p.name: (p.read_bytes(), p.stat())
            for p in (root / ".current-industry-classification-v1").iterdir()
        }
        observations.append((value.known_at, files))
        if expired:
            kwargs["clock"].__self__.value += timedelta(minutes=30)
        return value

    monkeypatch.setattr(archive.FileCurrentIndustryArchiveV1, "archive_exact", observe)
    result = _run_api(root, path, members, kwargs)["cohort_context"][
        "industry_participation"
    ]
    if expired:
        assert result["availability"] == "INSUFFICIENT_EVIDENCE"
        assert result["reasons"] == ["ACQUISITION_CUTOFF_EXCEEDED"]
        assert result["fact"] is None
    else:
        assert result["availability"] == "OBSERVED"
        assert result["known_at"] == api._instant(observations[0][0])
    current = {
        p.name: (p.read_bytes(), p.stat())
        for p in (root / ".current-industry-classification-v1").iterdir()
    }
    for name, (raw, info) in observations[0][1].items():
        assert current[name][0] == raw
        assert current[name][1].st_ino == info.st_ino
        assert current[name][1].st_mtime_ns == info.st_mtime_ns
        assert current[name][1].st_ctime_ns == info.st_ctime_ns


@pytest.mark.parametrize("expired", [False, True])
def test_industry_corruption_during_final_context_validation_is_fatal(
    tmp_path, monkeypatch, capsys, expired
):
    root, path, members, kwargs, _, _ = _setup(tmp_path, monkeypatch)
    original = api._revalidate_context
    if expired:
        retain = archive.FileCurrentIndustryArchiveV1.archive_exact

        def expire(self, *args, **options):
            value = retain(self, *args, **options)
            kwargs["clock"].__self__.value += timedelta(minutes=30)
            return value

        monkeypatch.setattr(
            archive.FileCurrentIndustryArchiveV1, "archive_exact", expire
        )

    def damage(*args, **options):
        value = original(*args, **options)
        directory = root / ".current-industry-classification-v1"
        if tuple(directory.glob("raw-*.csv")):
            _damage(root, "raw-*.csv")
        return value

    monkeypatch.setattr(api, "_revalidate_context", damage)
    _assert_fatal_output(capsys, _run_cli(monkeypatch, root, path, members, kwargs))
