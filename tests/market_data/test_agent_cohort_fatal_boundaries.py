"""Real retained cohort integrity wins over optional failure and interruption."""

from __future__ import annotations

import json

import pytest
from test_agent_cohort_integration import _setup

from swing_trading_ai_assistant.market_data import agent_cohort_context as api
from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


def _run_cli(monkeypatch, root, mapping_file, members, kwargs):
    original = api.run_agent_cohort_research_current

    def runner(symbols, storage_root, **provided):
        provided.update(kwargs)
        return original(symbols, storage_root, **provided)

    monkeypatch.setattr(cli, "run_agent_cohort_research_current", runner)
    arguments = [
        "research-run-current",
        "--symbol",
        "PNB",
        "--storage-root",
        str(root),
        "--output",
        "json",
        "--contract-version",
        "v4",
        "--context-purpose",
        "Explicit cohort",
        "--context-mappings-file",
        str(mapping_file),
    ]
    for member in members:
        arguments.extend(("--context-symbol", member.effective_symbol))
    return cli.main(arguments)


def _assert_fatal_output(capsys, code):
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert output.err == "internal_error\n"


def test_held_root_is_fatal_before_stock_or_cohort_effects(
    tmp_path, monkeypatch, capsys
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    calls = []
    kwargs["research"] = lambda *a, **k: calls.append(a)
    held = StorageRootLease.try_acquire_existing(root)
    assert held.lease is not None
    with held.lease:
        code = _run_cli(monkeypatch, root, path, members, kwargs)
    _assert_fatal_output(capsys, code)
    assert calls == source.calls == adjusted.calls == []


def test_replaced_root_and_industry_unavailability_are_fatal(
    tmp_path, monkeypatch, capsys
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    moved = root.with_name(root.name + "-replaced")
    calls = []

    def replace(url, headers):
        # The context was committed under the original root before this effect.
        assert list(root.rglob("completion-*.json"))
        calls.append(url)
        root.rename(moved)
        root.mkdir(mode=0o700)
        return HttpResponse(
            503, b"private source body", request_url=url, response_url=url
        )

    source.get = replace
    code = _run_cli(monkeypatch, root, path, members, kwargs)
    _assert_fatal_output(capsys, code)
    assert len(calls) == 1
    assert len(adjusted.calls) == 2
    assert list(moved.rglob("completion-*.json"))


@pytest.mark.parametrize("artifact", ["retained", "completion"])
@pytest.mark.parametrize("mutation", ["corrupt", "substitute"])
def test_receipt_or_marker_damage_wins_over_optional_industry_failure(
    tmp_path, monkeypatch, capsys, artifact, mutation
):
    root, path, members, kwargs, source, adjusted = _setup(tmp_path, monkeypatch)
    calls = []

    def damage(url, headers):
        contexts = list(root.rglob("context-*.json"))
        assert len(contexts) == 1
        context = contexts[0]
        target = context.with_name(context.name.replace("context-", artifact + "-", 1))
        assert target.is_file()
        original = target.read_bytes()
        inode = target.stat().st_ino
        if mutation == "corrupt":
            target.write_bytes(b"corrupt retained artifact")
            assert target.read_bytes() != original
        else:
            # Equal bytes are insufficient: replace the admitted filesystem object.
            replacement = target.with_suffix(".replacement")
            replacement.write_bytes(original)
            replacement.chmod(target.stat().st_mode & 0o777)
            replacement.replace(target)
            assert target.read_bytes() == original
            assert target.stat().st_ino != inode
        calls.append(url)
        return HttpResponse(
            503, b"private source body", request_url=url, response_url=url
        )

    source.get = damage
    code = _run_cli(monkeypatch, root, path, members, kwargs)
    _assert_fatal_output(capsys, code)
    assert len(calls) == 1
    assert len(adjusted.calls) == 2


@pytest.mark.parametrize("boundary", ["context", "completion"])
@pytest.mark.parametrize("after_publication", [False, True])
def test_interruption_around_context_publication_never_emits_partial_json(
    tmp_path, monkeypatch, capsys, boundary, after_publication
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    publish = api.regime._publish_exact
    interrupted = []

    def interrupt(directory, name, raw, maximum):
        if not name.startswith(boundary + "-"):
            return publish(directory, name, raw, maximum)
        if after_publication:
            publish(directory, name, raw, maximum)
        interrupted.append(name)
        raise KeyboardInterrupt("private interruption detail")

    monkeypatch.setattr(api.regime, "_publish_exact", interrupt)
    with pytest.raises(KeyboardInterrupt, match="private interruption detail"):
        _run_cli(monkeypatch, root, path, members, kwargs)
    output = capsys.readouterr()
    assert output.out == output.err == ""
    assert len(interrupted) == 1
    assert bool(list(root.rglob(interrupted[0]))) is after_publication
    assert source.calls == []
    # An interrupted command must release storage authority for an explicit retry.
    retry = StorageRootLease.try_acquire_existing(root)
    assert retry.lease is not None
    retry.lease.close()


@pytest.mark.parametrize("after_commit", [False, True])
def test_explicit_command_after_context_interruption_preserves_commit_boundary(
    tmp_path, monkeypatch, capsys, after_commit
):
    root, path, members, kwargs, source, _ = _setup(tmp_path, monkeypatch)
    publish = api.regime._publish_exact
    completed = []

    def interrupt(directory, name, raw, maximum):
        result = publish(directory, name, raw, maximum)
        if name.startswith("completion-"):
            completed.append(name)
            raise KeyboardInterrupt
        return result

    archive_type = api.regime.FileCurrentSamePassMarketContextArchiveV1
    archive_exact = archive_type.archive_exact

    def interrupt_committed(self, *args, **options):
        retained = archive_exact(self, *args, **options)
        assert type(retained) is api.regime.RetainedCurrentSamePassMarketContextV4
        completed.append(next(root.rglob("completion-*.json")).name)
        raise KeyboardInterrupt

    if after_commit:
        monkeypatch.setattr(archive_type, "archive_exact", interrupt_committed)
    else:
        monkeypatch.setattr(api.regime, "_publish_exact", interrupt)
    with pytest.raises(KeyboardInterrupt):
        _run_cli(monkeypatch, root, path, members, kwargs)
    output = capsys.readouterr()
    assert output.out == output.err == ""
    assert len(completed) == 1
    marker = next(root.rglob(completed[0]))
    original_files = {p: p.read_bytes() for p in marker.parent.iterdir() if p.is_file()}
    assert source.calls == []

    monkeypatch.setattr(api.regime, "_publish_exact", publish)
    monkeypatch.setattr(archive_type, "archive_exact", archive_exact)
    code = _run_cli(monkeypatch, root, path, members, kwargs)
    output = capsys.readouterr()
    assert all(p.read_bytes() == original for p, original in original_files.items())
    if not after_commit:
        # A marker without the final admissibility guard is not a completed commit.
        assert code == 2
        assert output.out == ""
        assert output.err == "internal_error\n"
        assert source.calls == []
        return
    # This unchanged synthetic stock fixture has usable price facts.
    assert code == 0, output.err
    assert output.err == ""
    report = json.loads(output.out)
    assert report["cohort_context"]["market_regime"]["availability"] == "OBSERVED"
    assert (
        report["cohort_context"]["industry_participation"]["availability"] == "OBSERVED"
    )
    assert len(source.calls) == 1
    assert all(p.read_bytes() == original for p, original in original_files.items())
