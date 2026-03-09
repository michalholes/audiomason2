from __future__ import annotations

import sys
from pathlib import Path


def _import_am_patch():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.errors import RunnerError
    from am_patch.run_result import _normalize_failure_summary
    from am_patch.runtime import _parse_gate_list, _stage_rank

    return RunnerError, _normalize_failure_summary, _parse_gate_list, _stage_rank


def test_normalize_failure_summary_maps_gate_failures() -> None:
    runner_error_cls, _normalize_failure_summary, parse_gate_list, stage_rank = _import_am_patch()

    stage, reason = _normalize_failure_summary(
        error=runner_error_cls("GATES", "GATES", "gates failed: ruff, pytest"),
        primary_fail_stage=None,
        secondary_failures=[],
        parse_gate_list=parse_gate_list,
        stage_rank=stage_rank,
    )

    assert stage == "GATE_RUFF, GATE_PYTEST"
    assert reason == "gates failed"


def test_normalize_failure_summary_maps_audit_failures() -> None:
    runner_error_cls, _normalize_failure_summary, parse_gate_list, stage_rank = _import_am_patch()

    stage, reason = _normalize_failure_summary(
        error=runner_error_cls("AUDIT", "AUDIT_REPORT_FAILED", "audit/audit_report.py failed"),
        primary_fail_stage=None,
        secondary_failures=[],
        parse_gate_list=parse_gate_list,
        stage_rank=stage_rank,
    )

    assert stage == "AUDIT"
    assert reason == "audit failed"


def test_normalize_failure_summary_keeps_preflight_reason_generic() -> None:
    runner_error_cls, _normalize_failure_summary, parse_gate_list, stage_rank = _import_am_patch()

    stage, reason = _normalize_failure_summary(
        error=runner_error_cls(
            "PREFLIGHT",
            "PATCH_ASCII",
            "patch contains non-ascii characters: patch.zip",
        ),
        primary_fail_stage=None,
        secondary_failures=[],
        parse_gate_list=parse_gate_list,
        stage_rank=stage_rank,
    )

    assert stage == "PREFLIGHT"
    assert reason == "invalid inputs"
