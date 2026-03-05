
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_git_add_file_patch, write_zip


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    rel = "docs/badguys_batch1/ignore_py.txt"
    p = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_ignore_py.patch"
    write_git_add_file_patch(p, rel, "patch-wins")

    py_bytes = (
        b"from __future__ import annotations\n"
        b"FILES = ['docs/badguys_batch1/ignore_py.txt']\n"
        b"from pathlib import Path\n"
        b"REPO = Path(__file__).resolve().parents[1]\n"
        b"(REPO / 'docs/badguys_batch1/ignore_py.txt').write_text('py-wins\n', encoding='utf-8')\n"
    )

    zip_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_ignore_py.zip"
    write_zip(zip_path, [("x.patch", p.read_bytes()), ("evil.py", py_bytes)])

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: unified ignores py",
        str(zip_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[p, zip_path],
    )


TEST = {
    "name": "test_052_unified_patch_ignores_py_when_patch_present",
    "makes_commit": False,
    "run": run,
}
