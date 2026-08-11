"""ARK-93 deterministic threshold derivation from retained benchmark evidence."""

from dataclasses import dataclass
from pathlib import Path

import ark93_benchmark_threshold_decision as threshold_decision
import pytest
from ark92_benchmark_baseline_collection import _ArtifactCliFailure, _SourceIdentityV1
from ark93_benchmark_threshold_decision import (
    ThresholdStatusV1,
    derive_workload_threshold,
    summarize_values,
)


def test_summary_uses_frozen_five_value_rule_and_direction() -> None:
    lower = summarize_values("elapsed_wall_ms", (9, 5, 7, 8, 6), "LOWER")
    higher = summarize_values(
        "throughput_rows_per_s", (90.0, 50.0, 70.0, 80.0, 60.0), "HIGHER"
    )

    assert lower.sorted_values == (5, 6, 7, 8, 9)
    assert (lower.minimum, lower.median, lower.maximum, lower.spread) == (5, 7, 9, 2)
    assert lower.threshold == 13
    assert lower.stable is True
    assert higher.threshold == 10.0


def test_zero_and_unstable_summaries_follow_plan03() -> None:
    zero = summarize_values("fd", (0, 0, 0, 0, 0), "LOWER")
    unstable = summarize_values("wall", (1, 2, 3, 20, 30), "LOWER")

    assert zero.stable is True
    assert zero.threshold == 0
    assert unstable.stable is False
    assert unstable.threshold is None


@dataclass(frozen=True)
class _Record:
    outcome: str = "SUCCEEDED"
    resource_evidence_status: str = "VALID"
    comparability_key: object = "same"
    elapsed_wall_ms: int = 10
    phase_elapsed_ms: dict[str, int | None] | None = None
    throughput_rows_per_s: float | None = 100.0
    peak_rss_bytes: int | None = 1_000
    open_fd_start: int | None = 4
    open_fd_peak: int | None = 6
    open_fd_end: int | None = 4
    query_elapsed_ms: int | None = None


def test_workload_decision_accepts_stable_exact_evidence() -> None:
    records = tuple(
        _Record(elapsed_wall_ms=value, peak_rss_bytes=1_000 + value)
        for value in (10, 11, 12, 13, 14)
    )

    decision = derive_workload_threshold("B01", records, "BASELINE")

    assert decision.status is ThresholdStatusV1.THRESHOLD_ACCEPTED
    assert decision.evidence_source == "BASELINE"
    assert {metric.metric for metric in decision.metrics} == {
        "elapsed_wall_ms",
        "throughput_rows_per_s",
        "peak_rss_bytes",
        "open_fd_peak_delta",
    }


def test_workload_decision_is_unset_for_noncomparable_or_unclosed_evidence() -> None:
    noncomparable = tuple(
        _Record(comparability_key="different" if index == 4 else "same")
        for index in range(5)
    )
    unclosed = tuple(_Record(open_fd_end=5) for _ in range(5))

    assert (
        derive_workload_threshold("B03", noncomparable, "B03_REPAIR").status
        is ThresholdStatusV1.UNSET
    )
    assert (
        derive_workload_threshold("B03", unclosed, "B03_REPAIR").status
        is ThresholdStatusV1.UNSET
    )


def _cli_args(root: Path) -> list[str]:
    return [
        "--output",
        str(root / "new" / "decision.json"),
        "--base-artifact",
        str(root / "baseline.json"),
        "--b03-repair-artifact",
        str(root / "repair.json"),
        "--expected-revision",
        "a" * 40,
        "--expected-tree",
        "b" * 40,
    ]


def _assert_sanitized_admission_failure(
    root: Path, capsys: pytest.CaptureFixture[str], exit_code: int
) -> None:
    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "threshold decision failed: SOURCE_ADMISSION_FAILED\n"
    assert str(root) not in captured.err
    assert not (root / "new").exists()


def test_cli_sanitizes_invalid_source_pin_before_output_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        threshold_decision,
        "_artifact_path",
        lambda path, _label: path,
    )
    arguments = _cli_args(tmp_path)
    arguments[-4:] = ["--expected-revision", "bad", "--expected-tree", "bad"]

    exit_code = threshold_decision.main(arguments)

    _assert_sanitized_admission_failure(tmp_path, capsys, exit_code)


@pytest.mark.parametrize(
    "failure_code",
    ("SOURCE_UNCLEAN", "SOURCE_UNTRUSTED_IMPORT_PATH", "SOURCE_MODULE_MISMATCH"),
)
def test_cli_sanitizes_source_and_module_admission_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure_code: str,
) -> None:
    identity = _SourceIdentityV1("a" * 40, "b" * 40, "c" * 64)
    monkeypatch.setattr(threshold_decision, "_artifact_path", lambda path, _label: path)
    monkeypatch.setattr(
        threshold_decision, "_expected_source_identity", lambda *_args: identity
    )
    monkeypatch.setattr(threshold_decision, "_source_identity_matches", lambda _: True)
    if failure_code == "SOURCE_MODULE_MISMATCH":
        monkeypatch.setattr(
            threshold_decision, "_capture_source_identity", lambda: identity
        )
        monkeypatch.setattr(
            threshold_decision,
            "_verify_loaded_module_snapshot",
            lambda _identity: (_ for _ in ()).throw(_ArtifactCliFailure(failure_code)),
        )
    else:
        monkeypatch.setattr(
            threshold_decision,
            "_capture_source_identity",
            lambda: (_ for _ in ()).throw(_ArtifactCliFailure(failure_code)),
        )

    exit_code = threshold_decision.main(_cli_args(tmp_path))

    _assert_sanitized_admission_failure(tmp_path, capsys, exit_code)
