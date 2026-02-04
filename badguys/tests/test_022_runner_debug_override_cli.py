from __future__ import annotations

from badguys._util import FuncStep, Plan, write_text


def run(ctx) -> Plan:
    cfg_path = ctx.repo_root / "patches" / "badguys_test_022_config.toml"

    def _write_cfg() -> None:
        write_text(
            cfg_path,
            """[suite]
issue_id = "666"
runner_cmd = ["python3", "scripts/am_patch.py"]
runner_verbosity = "quiet"
console_verbosity = "quiet"
log_verbosity = "quiet"
patches_dir = "patches"
logs_dir = "patches/badguys_logs"
central_log_pattern = "patches/badguys_{run_id}.log"
commit_limit = 0

[lock]
path = "patches/badguys.lock"
ttl_seconds = 3600
on_conflict = "fail"

[guard]
require_guard_test = true
guard_test_name = "test_000_test_mode_smoke"
abort_on_guard_fail = true

[filters]
include = []
exclude = []
""",
        )

    def _assert_cfg() -> None:
        from badguys.run_suite import _make_cfg

        cfg = _make_cfg(ctx.repo_root, cfg_path.relative_to(ctx.repo_root), "debug", None, None)
        joined = " ".join(cfg.runner_cmd)
        assert "--verbosity=debug" in joined, f"FAIL: expected --verbosity=debug in runner_cmd, got: {joined}"
        assert "--verbosity=quiet" not in joined, f"FAIL: cli override did not replace quiet, got: {joined}"

    return Plan(
        steps=[FuncStep(name="write_cfg", fn=_write_cfg), FuncStep(name="assert_cfg", fn=_assert_cfg)],
        cleanup_paths=[cfg_path],
    )


TEST = {
    "name": "test_022_runner_debug_override_cli",
    "run": run,
}
