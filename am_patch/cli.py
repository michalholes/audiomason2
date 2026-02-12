from __future__ import annotations

import argparse
from pathlib import Path

from .compat import import_legacy
from .model import CLIArgs
from .plan import build_plan, render_plan_summary


def _resolve_repo_root() -> Path:
    # Repo root == parent directory of this package.
    return Path(__file__).resolve().parents[1]


def parse_shadow_args(argv: list[str]) -> CLIArgs:
    """Parse args for the shadow runner (planning-only).

    This parser intentionally stays minimal. It is used by `python -m am_patch`.
    """

    p = argparse.ArgumentParser(prog="python -m am_patch", add_help=True)

    p.add_argument("issue_id", nargs="?", help="Issue id (e.g., 800)")
    p.add_argument("commit_message", nargs="?", help="Commit message (workspace mode)")
    p.add_argument("patch_input", nargs="?", help="Patch input (workspace mode)")

    p.add_argument("--config", dest="config_path", metavar="PATH", default=None)

    v = p.add_mutually_exclusive_group()
    v.add_argument("-q", "--quiet", dest="verbosity", action="store_const", const="quiet")
    v.add_argument("-v", "--verbose", dest="verbosity", action="store_const", const="verbose")
    v.add_argument("-n", "--normal", dest="verbosity", action="store_const", const="normal")
    v.add_argument("-d", "--debug", dest="verbosity", action="store_const", const="debug")
    v.add_argument(
        "--verbosity",
        dest="verbosity",
        choices=["debug", "verbose", "normal", "quiet"],
        default=None,
    )

    p.add_argument("--test-mode", dest="test_mode", action="store_true", default=None)
    p.add_argument("--update-workspace", dest="update_workspace", action="store_true", default=None)
    p.add_argument("-u", "--unified-patch", dest="unified_patch", action="store_true", default=None)

    p.add_argument(
        "-f",
        "--finalize-live",
        dest="finalize_message",
        metavar="MESSAGE",
        default=None,
        help="Finalize live repo (planning-only).",
    )
    p.add_argument(
        "-w",
        "--finalize-workspace",
        dest="finalize_workspace_issue_id",
        metavar="ISSUE_ID",
        default=None,
        help="Finalize an existing workspace for ISSUE_ID (planning-only).",
    )

    ns = p.parse_args(argv)

    return CLIArgs(
        issue_id=str(ns.issue_id) if ns.issue_id is not None else None,
        commit_message=str(ns.commit_message) if ns.commit_message is not None else None,
        patch_input=str(ns.patch_input) if ns.patch_input is not None else None,
        finalize_message=str(ns.finalize_message) if ns.finalize_message is not None else None,
        finalize_workspace_issue_id=(
            str(ns.finalize_workspace_issue_id) if ns.finalize_workspace_issue_id is not None else None
        ),
        config_path=str(ns.config_path) if ns.config_path is not None else None,
        verbosity=str(ns.verbosity) if ns.verbosity is not None else None,
        test_mode=bool(ns.test_mode) if ns.test_mode is not None else None,
        update_workspace=bool(ns.update_workspace) if ns.update_workspace is not None else None,
        unified_patch=bool(ns.unified_patch) if ns.unified_patch is not None else None,
    )


def shadow_main(argv: list[str] | None = None) -> int:
    import sys

    args = parse_shadow_args(sys.argv[1:] if argv is None else argv)
    repo_root = _resolve_repo_root()
    plan = build_plan(repo_root, args)
    sys.stdout.write(render_plan_summary(plan))
    return 0


# ----------------------------------------------------------------------------
# Legacy runner compatibility re-export
# ----------------------------------------------------------------------------

try:
    _legacy_cli = import_legacy("cli")
    parse_args = _legacy_cli.parse_args
except Exception:
    # Keep shadow runner usable even if legacy cannot be loaded.
    pass
