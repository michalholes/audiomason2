from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _import_gate():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.gate_dont_touch import run_dont_touch_gate

    return run_dont_touch_gate


def test_protected_file() -> None:
    run_dont_touch_gate = _import_gate()
    ok, protected, decision = run_dont_touch_gate(["pyproject.toml"], ["pyproject.toml"])
    assert ok is False
    assert protected == "pyproject.toml"
    assert decision == "pyproject.toml"


def test_directory_protection() -> None:
    run_dont_touch_gate = _import_gate()
    ok, protected, decision = run_dont_touch_gate(["scripts/x.py"], ["scripts/"])
    assert ok is False
    assert protected == "scripts/"
    assert decision == "scripts/x.py"


def test_non_protected() -> None:
    run_dont_touch_gate = _import_gate()
    ok, protected, decision = run_dont_touch_gate(["README.md"], ["pyproject.toml"])
    assert ok is True
    assert protected is None
    assert decision is None


def test_skip_flag() -> None:
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))

    from am_patch.errors import RunnerError
    from am_patch.gates import run_gates

    class DummyLogger:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def warning_core(self, msg: str) -> None:
            self.warnings.append(msg)

        def line(self, _msg: str) -> None:
            return None

        def error_core(self, _msg: str) -> None:
            raise AssertionError("dont-touch gate must be SKIP when skip flag is set")

        def section(self, _msg: str) -> None:
            return None

    logger = DummyLogger()

    # Gate must not execute; do not require a real repo.
    run_gates(
        logger,  # type: ignore[arg-type]
        cwd=Path("."),
        repo_root=Path("."),
        run_all=False,
        compile_check=False,
        compile_targets=[],
        compile_exclude=[],
        allow_fail=False,
        skip_ruff=True,
        skip_js=True,
        skip_biome=True,
        skip_typescript=True,
        skip_pytest=True,
        skip_mypy=True,
        skip_docs=True,
        skip_dont_touch=True,
        dont_touch_paths=["pyproject.toml"],
        skip_monolith=True,
        gate_monolith_enabled=False,
        gate_monolith_mode="strict",
        gate_monolith_scan_scope="patch",
        gate_monolith_extensions=None,
        gate_monolith_compute_fanin=False,
        gate_monolith_on_parse_error="fail",
        gate_monolith_areas_prefixes=[],
        gate_monolith_areas_names=[],
        gate_monolith_areas_dynamic=[],
        gate_monolith_large_loc=900,
        gate_monolith_huge_loc=1300,
        gate_monolith_large_allow_loc_increase=20,
        gate_monolith_huge_allow_loc_increase=0,
        gate_monolith_large_allow_exports_delta=2,
        gate_monolith_huge_allow_exports_delta=0,
        gate_monolith_large_allow_imports_delta=1,
        gate_monolith_huge_allow_imports_delta=0,
        gate_monolith_new_file_max_loc=400,
        gate_monolith_new_file_max_exports=25,
        gate_monolith_new_file_max_imports=15,
        gate_monolith_hub_fanin_delta=5,
        gate_monolith_hub_fanout_delta=5,
        gate_monolith_hub_exports_delta_min=3,
        gate_monolith_hub_loc_delta_min=100,
        gate_monolith_crossarea_min_distinct_areas=3,
        gate_monolith_catchall_basenames=[],
        gate_monolith_catchall_dirs=[],
        gate_monolith_catchall_allowlist=[],
        docs_include=[],
        docs_exclude=[],
        docs_required_files=[],
        js_extensions=[],
        js_command=[],
        biome_extensions=[],
        biome_command=[],
        biome_format=True,
        biome_format_command=[],
        biome_autofix=True,
        biome_fix_command=[],
        typescript_extensions=[],
        typescript_command=[],
        gate_typescript_mode="auto",
        typescript_targets=[],
        gate_typescript_base_tsconfig="tsconfig.json",
        ruff_format=False,
        ruff_autofix=False,
        ruff_targets=[],
        pytest_targets=[],
        mypy_targets=[],
        gate_ruff_mode="auto",
        gate_mypy_mode="auto",
        gate_pytest_mode="auto",
        gate_pytest_js_prefixes=[],
        gates_order=["dont-touch"],
        pytest_use_venv=False,
        decision_paths=["pyproject.toml"],
        progress=None,
    )

    assert "gate_dont_touch=SKIP (skipped_by_user)" in logger.warnings

    # Verify non-skip blocks.

    class DummyLogger2:
        def warning_core(self, _msg: str) -> None:
            return None

        def line(self, _msg: str) -> None:
            return None

        def error_core(self, _msg: str) -> None:
            return None

        def section(self, _msg: str) -> None:
            return None

    logger2 = DummyLogger2()

    with pytest.raises(RunnerError):
        run_gates(
            logger2,  # type: ignore[arg-type]
            cwd=Path("."),
            repo_root=Path("."),
            run_all=False,
            compile_check=False,
            compile_targets=[],
            compile_exclude=[],
            allow_fail=False,
            skip_ruff=True,
            skip_js=True,
            skip_biome=True,
            skip_typescript=True,
            skip_pytest=True,
            skip_mypy=True,
            skip_docs=True,
            skip_dont_touch=False,
            dont_touch_paths=["pyproject.toml"],
            skip_monolith=True,
            gate_monolith_enabled=False,
            gate_monolith_mode="strict",
            gate_monolith_scan_scope="patch",
            gate_monolith_extensions=None,
            gate_monolith_compute_fanin=False,
            gate_monolith_on_parse_error="fail",
            gate_monolith_areas_prefixes=[],
            gate_monolith_areas_names=[],
            gate_monolith_areas_dynamic=[],
            gate_monolith_large_loc=900,
            gate_monolith_huge_loc=1300,
            gate_monolith_large_allow_loc_increase=20,
            gate_monolith_huge_allow_loc_increase=0,
            gate_monolith_large_allow_exports_delta=2,
            gate_monolith_huge_allow_exports_delta=0,
            gate_monolith_large_allow_imports_delta=1,
            gate_monolith_huge_allow_imports_delta=0,
            gate_monolith_new_file_max_loc=400,
            gate_monolith_new_file_max_exports=25,
            gate_monolith_new_file_max_imports=15,
            gate_monolith_hub_fanin_delta=5,
            gate_monolith_hub_fanout_delta=5,
            gate_monolith_hub_exports_delta_min=3,
            gate_monolith_hub_loc_delta_min=100,
            gate_monolith_crossarea_min_distinct_areas=3,
            gate_monolith_catchall_basenames=[],
            gate_monolith_catchall_dirs=[],
            gate_monolith_catchall_allowlist=[],
            docs_include=[],
            docs_exclude=[],
            docs_required_files=[],
            js_extensions=[],
            js_command=[],
            biome_extensions=[],
            biome_command=[],
            biome_format=True,
            biome_format_command=[],
            biome_autofix=True,
            biome_fix_command=[],
            typescript_extensions=[],
            typescript_command=[],
            gate_typescript_mode="auto",
            typescript_targets=[],
            gate_typescript_base_tsconfig="tsconfig.json",
            ruff_format=False,
            ruff_autofix=False,
            ruff_targets=[],
            pytest_targets=[],
            mypy_targets=[],
            gate_ruff_mode="auto",
            gate_mypy_mode="auto",
            gate_pytest_mode="auto",
            gate_pytest_js_prefixes=[],
            gates_order=["dont-touch"],
            pytest_use_venv=False,
            decision_paths=["pyproject.toml"],
            progress=None,
        )
