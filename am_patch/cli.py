from __future__ import annotations

import argparse
from pathlib import Path

from .compat import import_legacy
from .model import CLIArgs
from .plan import build_plan, render_plan_summary
from .runner import execute_plan


def _resolve_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _looks_like_patch(s: str) -> bool:
    ss = s.lower()
    return ss.endswith(".zip") or ss.endswith(".patch") or ss.endswith(".diff")


def parse_shadow_args(argv: list[str]) -> tuple[CLIArgs, bool]:
    p = argparse.ArgumentParser(prog="python -m am_patch", add_help=True)

    p.add_argument("--plan", dest="plan_only", action="store_true", help="Print plan only")

    p.add_argument("-f", "--finalize-live", dest="finalize_message", metavar="MESSAGE", default=None)
    p.add_argument(
        "--finalize-workspace",
        dest="finalize_workspace",
        action="store_true",
        default=None,
        help="Promote workspace to live (root runner).",
    )

    p.add_argument("issue_id", nargs="?", help="Issue id (e.g., 801)")
    p.add_argument("arg2", nargs="?", help="Patch input or commit message")
    p.add_argument("arg3", nargs="?", help="Patch input (when arg2 is commit message)")

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

    ns = p.parse_args(argv)

    issue_id = str(ns.issue_id) if ns.issue_id is not None else None

    commit_message: str | None = None
    patch_input: str | None = None
    if ns.arg2 is not None and ns.arg3 is None:
        if _looks_like_patch(str(ns.arg2)):
            patch_input = str(ns.arg2)
        else:
            commit_message = str(ns.arg2)
    elif ns.arg2 is not None and ns.arg3 is not None:
        commit_message = str(ns.arg2)
        patch_input = str(ns.arg3)

    cli = CLIArgs(
        issue_id=issue_id,
        commit_message=commit_message,
        patch_input=patch_input,
        finalize_message=str(ns.finalize_message) if ns.finalize_message is not None else None,
        finalize_workspace=bool(ns.finalize_workspace) if ns.finalize_workspace is not None else None,
        config_path=str(ns.config_path) if ns.config_path is not None else None,
        verbosity=str(ns.verbosity) if ns.verbosity is not None else None,
        test_mode=bool(ns.test_mode) if ns.test_mode is not None else None,
        update_workspace=bool(ns.update_workspace) if ns.update_workspace is not None else None,
        unified_patch=bool(ns.unified_patch) if ns.unified_patch is not None else None,
    )
    return cli, bool(ns.plan_only)


def shadow_main(argv: list[str] | None = None) -> int:
    import sys

    cli, plan_only = parse_shadow_args(sys.argv[1:] if argv is None else argv)
    repo_root = _resolve_repo_root()
    plan = build_plan(repo_root, cli)

    sys.stdout.write(render_plan_summary(plan))
    if plan_only:
        return 0

    result = execute_plan(plan)
    return int(result.exit_code)


# ----------------------------------------------------------------------------
# Legacy runner compatibility re-export
# ----------------------------------------------------------------------------

try:
    _legacy_cli = import_legacy("cli")
    parse_args = _legacy_cli.parse_args
except Exception:
    pass
