from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ROOT = Path("/tmp/badguys_finalize_sandbox")
ORIGIN = SANDBOX_ROOT / "origin.git"
CLONE = SANDBOX_ROOT / "clone"

DEFAULT_USER_NAME = "badguys"
DEFAULT_USER_EMAIL = "badguys@example.invalid"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def _must_ok(p: subprocess.CompletedProcess[str], label: str) -> None:
    if p.returncode != 0:
        raise SystemExit(
            f"{label} failed rc={p.returncode}\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}"
        )


def setup() -> None:
    teardown()
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    # Build a local origin that already contains branch refs (origin/main must exist).
    _must_ok(_run(["git", "clone", "--bare", str(REPO_ROOT), str(ORIGIN)], cwd=SANDBOX_ROOT), "git clone --bare")

    # Clone from the local bare origin so remote-tracking refs (origin/main) are present.
    _must_ok(_run(["git", "clone", str(ORIGIN), str(CLONE)], cwd=SANDBOX_ROOT), "git clone (from origin)")

    # Configure identity for commits inside the sandbox clone
    _must_ok(_run(["git", "config", "user.name", DEFAULT_USER_NAME], cwd=CLONE), "git config user.name")
    _must_ok(_run(["git", "config", "user.email", DEFAULT_USER_EMAIL], cwd=CLONE), "git config user.email")

    # Ensure the sandbox clone can run gates: am_patch expects a venv at repo/.venv.
    src_venv = REPO_ROOT / ".venv"
    dst_venv = CLONE / ".venv"
    if not dst_venv.exists():
        if src_venv.exists():
            dst_venv.symlink_to(src_venv)
        else:
            raise SystemExit("venv not found at repo/.venv; cannot run sandbox finalize tests")

    # Ensure clean workspace in sandbox clone
    shutil.rmtree(CLONE / "patches" / "workspaces", ignore_errors=True)
    print(f"setup OK sandbox={SANDBOX_ROOT}")


def teardown() -> None:
    shutil.rmtree(SANDBOX_ROOT, ignore_errors=True)


def _make_change_in_clone(path_rel: str, content: str) -> None:
    p = CLONE / path_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _finalize_live(disable_promotion: bool, allow_gates_fail: bool) -> None:
    # Make a deterministic change so finalize-live has something to commit.
    _make_change_in_clone("badguys/tmp/finalize_live.txt", "finalize-live change\n")

    if allow_gates_fail:
        # Intentionally break a gate (syntax error) so -g is required.
        _make_change_in_clone("src/badguys_gate_fail.py", "def oops(:\n")

    flags: list[str] = []
    if disable_promotion:
        flags.append("--disable-promotion")
    if allow_gates_fail:
        flags.append("-g")

    cmd = ["python3", "scripts/am_patch.py", *flags, "-f", "badguys: finalize_live"]
    p = _run(cmd, cwd=CLONE)
    _must_ok(p, "am_patch finalize-live")

    # If promotion is enabled, there must be at least one commit reachable from HEAD
    # and the local bare origin should have refs.
    if not disable_promotion:
        p2 = _run(["git", "rev-parse", "HEAD"], cwd=CLONE)
        _must_ok(p2, "git rev-parse HEAD")
        p3 = _run(["git", "show-ref"], cwd=ORIGIN)
        _must_ok(p3, "git show-ref (origin)")
    print("finalize_live OK")


def _create_workspace_for_finalize_workspace(issue_id: str) -> None:
    # Create a workspace deterministically using a no-op patch with -n, but disable promotion
    # so the workspace is retained.
    patch_dir = CLONE / "patches"
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / "badguys_finalize_workspace_seed.py"

    patch_path.write_text(
        "FILES = [\n"
        "    'badguys/tmp/finalize_workspace_seed.txt',\n"
        "]\n"
        "from pathlib import Path\n"
        "p = Path('badguys/tmp/finalize_workspace_seed.txt')\n"
        "p.parent.mkdir(parents=True, exist_ok=True)\n"
        "p.write_text('seed\\n', encoding='utf-8')\n",
        encoding="utf-8",
    )

    cmd = [
        "python3",
        "scripts/am_patch.py",
        "--disable-promotion",
        "--keep-workspace",
        issue_id,
        "badguys: seed workspace",
        str(patch_path),
    ]
    p = _run(cmd, cwd=CLONE)
    _must_ok(p, "am_patch seed workspace")


def _finalize_workspace(issue_id: str, disable_promotion: bool) -> None:
    _create_workspace_for_finalize_workspace(issue_id)

    flags: list[str] = []
    if disable_promotion:
        flags.append("--disable-promotion")

    cmd = ["python3", "scripts/am_patch.py", *flags, "--finalize-workspace", issue_id]
    p = _run(cmd, cwd=CLONE)
    _must_ok(p, "am_patch finalize-workspace")
    print("finalize_workspace OK")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup")
    sub.add_parser("teardown")

    sp = sub.add_parser("finalize_live")
    sp.add_argument("--disable-promotion", action="store_true")
    sp.add_argument("--allow-gates-fail", action="store_true")

    spw = sub.add_parser("finalize_workspace")
    spw.add_argument("--disable-promotion", action="store_true")
    spw.add_argument("--issue-id", default="666")

    ns = ap.parse_args(argv)

    if ns.cmd == "setup":
        setup()
        return 0
    if ns.cmd == "teardown":
        teardown()
        return 0
    if ns.cmd == "finalize_live":
        if not CLONE.exists() or not ORIGIN.exists():
            raise SystemExit("sandbox not initialized; run: finalize_sandbox.py setup")
        _finalize_live(disable_promotion=bool(ns.disable_promotion), allow_gates_fail=bool(ns.allow_gates_fail))
        return 0
    if ns.cmd == "finalize_workspace":
        if not CLONE.exists() or not ORIGIN.exists():
            raise SystemExit("sandbox not initialized; run: finalize_sandbox.py setup")
        _finalize_workspace(issue_id=str(ns.issue_id), disable_promotion=bool(ns.disable_promotion))
        return 0

    raise SystemExit("unknown command")


if __name__ == "__main__":
    raise SystemExit(main(os.sys.argv[1:]))
