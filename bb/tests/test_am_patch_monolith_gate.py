from __future__ import annotations

import sys
from pathlib import Path


def _import_monolith_gate():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.log import Logger
    from am_patch.monolith_gate import run_monolith_gate

    return Logger, run_monolith_gate


def _make_logger(tmp_path: Path):
    Logger, _ = _import_monolith_gate()
    log_path = tmp_path / "log.txt"
    symlink_path = tmp_path / "current.log"
    return Logger(
        log_path=log_path,
        symlink_path=symlink_path,
        screen_level="quiet",
        log_level="debug",
        console_color="never",
        symlink_enabled=False,
    )


def test_monolith_core_boundary_violation_fails(tmp_path: Path) -> None:
    Logger, run_monolith_gate = _import_monolith_gate()

    repo_root = tmp_path / "repo_root"
    cwd = tmp_path / "cwd"
    repo_root.mkdir()
    cwd.mkdir()

    rel = Path("src/audiomason/coremod.py")
    (repo_root / rel.parent).mkdir(parents=True)
    (cwd / rel.parent).mkdir(parents=True)

    (repo_root / rel).write_text("def ok():\n    return 1\n", encoding="utf-8")
    (cwd / rel).write_text(
        "import plugins.foo\n\n"
        "def ok():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    logger = Logger(
        log_path=tmp_path / "log.txt",
        symlink_path=tmp_path / "current.log",
        screen_level="quiet",
        log_level="debug",
        console_color="never",
        symlink_enabled=False,
    )
    try:
        ok = run_monolith_gate(
            logger,
            cwd,
            repo_root=repo_root,
            decision_paths=[str(rel)],
            gate_monolith_mode="strict",
            gate_monolith_scan_scope="patch",
            gate_monolith_compute_fanin=False,
            gate_monolith_on_parse_error="fail",
            gate_monolith_areas=[
                {"prefix": "src/audiomason/", "area": "core"},
                {"prefix": "plugins/", "area": "plugins", "dynamic": "plugins.<name>"},
            ],
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
            gate_monolith_catchall_basenames=["utils.py"],
            gate_monolith_catchall_dirs=["utils"],
            gate_monolith_catchall_allowlist=[],
        )
        assert ok is False
    finally:
        logger.close()


def test_monolith_large_growth_loc_delta_fails(tmp_path: Path) -> None:
    Logger, run_monolith_gate = _import_monolith_gate()

    repo_root = tmp_path / "repo_root"
    cwd = tmp_path / "cwd"
    repo_root.mkdir()
    cwd.mkdir()

    rel = Path("scripts/am_patch/bigfile.py")
    (repo_root / rel.parent).mkdir(parents=True)
    (cwd / rel.parent).mkdir(parents=True)

    base_lines = ["x = 1\n"] * 900
    grown_lines = base_lines + (["y = 2\n"] * 21)

    (repo_root / rel).write_text("".join(base_lines), encoding="utf-8")
    (cwd / rel).write_text("".join(grown_lines), encoding="utf-8")

    logger = Logger(
        log_path=tmp_path / "log.txt",
        symlink_path=tmp_path / "current.log",
        screen_level="quiet",
        log_level="debug",
        console_color="never",
        symlink_enabled=False,
    )
    try:
        ok = run_monolith_gate(
            logger,
            cwd,
            repo_root=repo_root,
            decision_paths=[str(rel)],
            gate_monolith_mode="strict",
            gate_monolith_scan_scope="patch",
            gate_monolith_compute_fanin=False,
            gate_monolith_on_parse_error="fail",
            gate_monolith_areas=[
                {"prefix": "scripts/am_patch/", "area": "runner"},
            ],
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
        )
        assert ok is False
    finally:
        logger.close()
