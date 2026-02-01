from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from am_patch.version import RUNNER_VERSION


class AppendOverride(argparse.Action):
    """Append KEY=VALUE strings into ns.overrides."""

    def __init__(
        self,
        option_strings: list[str],
        dest: str,
        key: str,
        const_value: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._key = key
        self._const_value = const_value
        super().__init__(option_strings, dest, **kwargs)

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        ov = getattr(namespace, "overrides", None)
        if ov is None:
            ov = []
            namespace.overrides = ov
        if values is None:
            v = self._const_value if self._const_value is not None else "true"
        elif isinstance(values, str):
            v = values
        else:
            v = ",".join(str(x) for x in values)
        ov.append(f"{self._key}={v}")


@dataclass
class CliArgs:
    mode: str  # workspace|finalize|finalize_workspace
    issue_id: str | None
    patch_script: str | None
    message: str | None

    run_all_tests: bool | None
    allow_no_op: bool | None

    unified_patch: bool | None
    patch_strip: int | None
    skip_up_to_date: bool | None
    allow_non_main: bool | None

    # legacy (promotion rollback)
    no_rollback: bool | None

    update_workspace: bool | None
    soft_reset_workspace: bool | None
    enforce_allowed_files: bool | None

    # NEW controls
    rollback_workspace_on_fail: bool | None
    live_repo_guard: bool | None
    live_repo_guard_scope: str | None
    patch_jail: bool | None
    patch_jail_unshare_net: bool | None
    ruff_format: bool | None
    pytest_use_venv: bool | None

    overrides: list[str] | None
    require_push_success: bool | None
    allow_outside_files: bool | None
    allow_declared_untouched: bool | None
    disable_promotion: bool | None
    allow_live_changed: bool | None
    allow_gates_fail: bool | None
    skip_ruff: bool | None
    skip_pytest: bool | None
    skip_mypy: bool | None
    gates_order: str | None
    ruff_autofix_legalize_outside: bool | None
    post_success_audit: bool | None
    load_latest_patch: bool | None
    keep_workspace: bool | None
    test_mode: bool | None


def _fmt_short_help() -> str:
    return f"""am_patch.py (RUNNER_VERSION={RUNNER_VERSION})

Options:
  -h, --help
      Show short help with commonly used options.

  -H, --help-all
      Show full reference help with all available options and exit.

  -c, --show-config
      Print effective configuration and policy sources (defaults, config file,
      CLI overrides) and exit.

  -a, --allow-undeclared-paths
      Allow patch scripts to touch files outside declared FILES (override default FAIL).

  -t, --allow-untouched-files
      Allow declared but untouched FILES (override default FAIL).

  -l, --rerun-latest
      Rerun the latest archived patch for ISSUE_ID (auto-select from
      patches/successful and patches/unsuccessful).

  -r, --run-all-gates
      Run all gates (ruff, pytest, mypy) even if one fails.

  -g, --allow-gates-fail
      Allow gate failures and still promote; intended for bug bounty.

  -f, --finalize-live MESSAGE
      Finalize live repo using MESSAGE as commit message. Put all flags before -f/--finalize-live.

  --finalize-workspace ISSUE_ID
      Finalize existing workspace for ISSUE_ID; commit message is read from workspace meta.json.

  -n, --allow-no-op
      Allow no-op patches (override default FAIL).

  -u, --unified-patch
      Treat PATCH_PATH as a unified diff (.patch) or zip bundle of .patch files.

"""


def _fmt_full_help() -> str:
    return f"""am_patch.py (RUNNER_VERSION={RUNNER_VERSION})

Full reference of all available options.
All options are shown in long form.
Short aliases are shown in parentheses only for options that also appear in short help.

CORE / INFO
  --help (-h)
      Show short help with commonly used options.

  --help-all (-H)
      Show full reference help with all available options and exit.

  --show-config (-c)
      Print effective configuration and policy sources (defaults, config file,
      CLI overrides) and exit.

  --version
      Print runner version and exit.

WORKFLOW / MODES
  --finalize-live MESSAGE (-f)
      Finalize live repository using MESSAGE as commit message.
      Enables finalize mode and performs promotion, commit, and push.

  --finalize-workspace ISSUE_ID
      Finalize an existing workspace for ISSUE_ID, including promotion, gates, commit, and push.
      Commit message is read from workspace meta.json.

  --rerun-latest (-l)
      Rerun the latest archived patch for the given ISSUE_ID.
      Patch is auto-selected from successful or unsuccessful archives.

  --update-workspace
      Update the existing workspace to match the current live repository state.

  --test-mode
      Badguys test mode: run patch + gates in workspace, then stop.
      Skips promotion/live gates/commit/push and does not create any archives.
      Workspace is deleted on exit (success or failure).

GATES / EXECUTION
  --skip-ruff
      Skip ruff gate.
      [default: OFF]

  --skip-pytest
      Skip pytest gate.
      [default: OFF]

  --skip-mypy
      Skip mypy gate.
      [default: OFF]

  --gates-order CSV
      Gate execution order/selection as CSV (ruff,pytest,mypy). Empty means run no gates.
      [default: ruff,pytest,mypy]

  --run-all-gates (-r)
      Run all gates even if one fails.
      [default: OFF]

  --allow-gates-fail (-g)
      Allow gate failures and still promote; intended for bug bounty.
      [default: OFF]

POLICY OVERRIDES (COMMON)
  --allow-undeclared-paths (-a)
      Allow patch scripts to touch files outside declared FILES.
      [default: OFF]

  --allow-untouched-files (-t)
      Allow declared but untouched FILES.
      [default: OFF]

  --allow-no-op (-n)
      Allow no-op patches.
      [default: OFF]

PROMOTION / GIT
  --require-push-success
      Require git push success (override default allow-push-fail).
      [default: OFF]

  --disable-promotion
      Disable commit+push promotion.
      [default: OFF]

  --allow-live-changed
      Allow live-repo changes since base_sha for promoted files (override default FAIL).
      [default: OFF]

  --overwrite-live
      On LIVE_CHANGED: overwrite live repo with workspace.

  --overwrite-workspace
      On LIVE_CHANGED: keep live repo and drop those files from promotion.

  --overwrite-live
      On LIVE_CHANGED: overwrite live repo with workspace for the changed files.

  --overwrite-workspace
      On LIVE_CHANGED: keep live repo and drop those files from promotion.

SAFETY / CONSISTENCY
  --rollback-workspace-on-fail / --no-rollback-workspace-on-fail
      Roll back workspace to pre-patch state if patch or gates fail.
      [default: ON]

  --live-repo-guard / --no-live-repo-guard
      Fail if live repo changes during patching.
      [default: ON]

  --live-repo-guard-scope [patch|patch_and_gates]
      Live repo guard scope.
      [default: patch]

  --patch-jail / --no-patch-jail
      Execute patch script inside bubblewrap jail (bwrap).
      [default: ON]

  --patch-jail-unshare-net / --no-patch-jail-unshare-net
      When patch_jail is enabled, unshare network namespace.
      [default: ON]

TOOLING INTEGRATION
  --ruff-format / --no-ruff-format
      Run `ruff format` before ruff check.
      [default: ON]

  --pytest-use-venv / --no-pytest-use-venv
      Run pytest with live repo .venv python.
      [default: ON]

  --ruff-autofix-legalize-outside / --no-ruff-autofix-legalize-outside
      When ruff_autofix is enabled, automatically legalize ruff-only fixes
      outside FILES (bounded to ruff_targets).
      [default: ON]

UNIFIED PATCH INPUT
  -u, --unified-patch
      Treat PATCH_PATH as a unified diff (.patch) or zip bundle of .patch files.

  -p N, --patch-strip N
      Strip N leading path components when applying unified patches (like patch -pN).

POST-SUCCESS ACTIONS
  --post-success-audit / --no-post-success-audit
      Run audit report after a successful promotion and push.
      [default: ON]

ADVANCED CONFIG / OVERRIDES
  --override KEY=VALUE
      Policy override(s) in KEY=VALUE form; may be repeated.

  --gates-order CSV
      Gate execution order/selection as CSV; empty disables all gates.

  --skip-up-to-date
      Skip up-to-date check.

  --allow-non-main
      Allow running on a non-main branch.

  --keep-workspace
      Keep workspace on success (override default delete).

  --soft-reset-workspace
      Soft reset workspace.

  --enforce-allowed-files
      Enforce allowed-files.

NOTES
  Short options exist only for options listed in short help. All other options are long-form only.

"""


def parse_args(argv: list[str]) -> CliArgs:
    # Explicit short/full help split (do not let argparse generate a chaotic -h).
    if "-h" in argv or "--help" in argv:
        print(_fmt_short_help())
        raise SystemExit(0)
    if "-H" in argv or "--help-all" in argv:
        print(_fmt_full_help())
        raise SystemExit(0)

    # Finalize strict rule: -f/--finalize-live MESSAGE must be the final tokens.
    for tok in ("-f", "--finalize-live"):
        if tok in argv:
            i = argv.index(tok)
            if i != len(argv) - 2:
                raise SystemExit(
                    "finalize mode (-f/--finalize-live) requires MESSAGE as the final argument; "
                    "put all flags before -f/--finalize-live"
                )

    p = argparse.ArgumentParser(
        prog="am_patch.py",
        description=f"am_patch RUNNER_VERSION={RUNNER_VERSION}",
        add_help=False,
    )
    p.add_argument(
        "--version", action="version", version=f"am_patch RUNNER_VERSION={RUNNER_VERSION}"
    )

    # Short-help set (short+long).
    p.add_argument(
        "-a",
        "--allow-undeclared-paths",
        dest="allow_outside_files",
        action="store_true",
        default=None,
    )
    p.add_argument(
        "-t",
        "--allow-untouched-files",
        dest="allow_declared_untouched",
        action="store_true",
        default=None,
    )
    p.add_argument(
        "-l", "--rerun-latest", dest="load_latest_patch", action="store_true", default=None
    )
    p.add_argument("-r", "--run-all-gates", dest="run_all_tests", action="store_true", default=None)
    p.add_argument(
        "-g", "--allow-gates-fail", dest="allow_gates_fail", action="store_true", default=None
    )
    p.add_argument("-n", "--allow-no-op", dest="allow_no_op", action="store_true", default=None)
    p.add_argument("-u", "--unified-patch", dest="unified_patch", action="store_true", default=None)
    p.add_argument("-p", "--patch-strip", dest="patch_strip", metavar="N", type=int, default=None)
    p.add_argument("-c", "--show-config", dest="show_config", action="store_true", default=False)
    p.add_argument(
        "-f", "--finalize-live", dest="finalize_message", metavar="MESSAGE", default=None
    )
    p.add_argument(
        "--finalize-workspace", dest="finalize_workspace_issue_id", metavar="ISSUE_ID", default=None
    )

    # Full-only options (long-only; no short aliases).
    p.add_argument(
        "--override", dest="overrides", action="append", default=None, metavar="KEY=VALUE"
    )
    p.add_argument(
        "--require-push-success", dest="require_push_success", action="store_true", default=None
    )
    p.add_argument(
        "--disable-promotion", dest="disable_promotion", action="store_true", default=None
    )
    p.add_argument(
        "--allow-live-changed", dest="allow_live_changed", action="store_true", default=None
    )
    p.add_argument(
        "--overwrite-live",
        dest="overrides",
        action=AppendOverride,
        key="live_changed_resolution",
        const_value="overwrite_live",
        nargs=0,
    )
    p.add_argument(
        "--overwrite-workspace",
        dest="overrides",
        action=AppendOverride,
        key="live_changed_resolution",
        const_value="overwrite_workspace",
        nargs=0,
    )
    p.add_argument("--keep-workspace", dest="keep_workspace", action="store_true", default=None)
    p.add_argument("--test-mode", dest="test_mode", action="store_true", default=None)

    p.add_argument("--skip-ruff", dest="skip_ruff", action="store_true", default=None)
    p.add_argument("--skip-pytest", dest="skip_pytest", action="store_true", default=None)
    p.add_argument("--skip-mypy", dest="skip_mypy", action="store_true", default=None)
    p.add_argument("--gates-order", dest="gates_order", nargs="?", const="", default=None)

    p.add_argument(
        "--ruff-autofix-legalize-outside",
        dest="ruff_autofix_legalize_outside",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    p.add_argument(
        "--rollback-workspace-on-fail",
        dest="rollback_workspace_on_fail",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--live-repo-guard",
        dest="live_repo_guard",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--live-repo-guard-scope",
        dest="live_repo_guard_scope",
        choices=["patch", "patch_and_gates"],
        default=None,
    )
    p.add_argument(
        "--patch-jail", dest="patch_jail", action=argparse.BooleanOptionalAction, default=None
    )
    p.add_argument(
        "--patch-jail-unshare-net",
        dest="patch_jail_unshare_net",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--ruff-format", dest="ruff_format", action=argparse.BooleanOptionalAction, default=None
    )
    p.add_argument(
        "--pytest-use-venv",
        dest="pytest_use_venv",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    p.add_argument(
        "--post-success-audit",
        dest="post_success_audit",
        action=argparse.BooleanOptionalAction,
        default=None,
    )

    p.add_argument("--skip-up-to-date", dest="skip_up_to_date", action="store_true", default=None)
    p.add_argument("--allow-non-main", dest="allow_non_main", action="store_true", default=None)
    p.add_argument("--update-workspace", dest="update_workspace", action="store_true", default=None)
    p.add_argument(
        "--soft-reset-workspace", dest="soft_reset_workspace", action="store_true", default=None
    )
    p.add_argument(
        "--enforce-allowed-files", dest="enforce_allowed_files", action="store_true", default=None
    )

    # Legacy (promotion rollback)
    p.add_argument(
        "--no-rollback-on-commit-push-failure",
        dest="no_rollback",
        action="store_true",
        default=None,
    )

    p.add_argument("rest", nargs="*")
    ns = p.parse_args(argv)

    # Normalize override keys to lowercase for deterministic behavior.
    if ns.overrides is not None:
        norm: list[str] = []
        for item in ns.overrides:
            if "=" in str(item):
                k, v = str(item).split("=", 1)
                norm.append(f"{k.strip().lower()}={v}")
            else:
                norm.append(str(item))
        ns.overrides = norm

    if ns.show_config:
        return CliArgs(
            mode="show_config",
            issue_id=None,
            patch_script=None,
            message=None,
            run_all_tests=ns.run_all_tests,
            allow_no_op=ns.allow_no_op,
            unified_patch=getattr(ns, "unified_patch", None),
            patch_strip=getattr(ns, "patch_strip", None),
            skip_up_to_date=ns.skip_up_to_date,
            allow_non_main=ns.allow_non_main,
            no_rollback=ns.no_rollback,
            update_workspace=ns.update_workspace,
            soft_reset_workspace=ns.soft_reset_workspace,
            enforce_allowed_files=ns.enforce_allowed_files,
            rollback_workspace_on_fail=ns.rollback_workspace_on_fail,
            live_repo_guard=ns.live_repo_guard,
            live_repo_guard_scope=ns.live_repo_guard_scope,
            patch_jail=ns.patch_jail,
            patch_jail_unshare_net=ns.patch_jail_unshare_net,
            ruff_format=ns.ruff_format,
            pytest_use_venv=ns.pytest_use_venv,
            overrides=ns.overrides,
            require_push_success=ns.require_push_success,
            allow_outside_files=ns.allow_outside_files,
            allow_declared_untouched=ns.allow_declared_untouched,
            disable_promotion=ns.disable_promotion,
            allow_live_changed=ns.allow_live_changed,
            allow_gates_fail=ns.allow_gates_fail,
            skip_ruff=ns.skip_ruff,
            skip_pytest=ns.skip_pytest,
            skip_mypy=ns.skip_mypy,
            gates_order=ns.gates_order,
            ruff_autofix_legalize_outside=ns.ruff_autofix_legalize_outside,
            load_latest_patch=ns.load_latest_patch,
            keep_workspace=ns.keep_workspace,
            test_mode=ns.test_mode,
            post_success_audit=ns.post_success_audit,
        )

    if ns.finalize_workspace_issue_id is not None:
        mode = "finalize_workspace"
        issue_id = str(ns.finalize_workspace_issue_id)
        if not issue_id.isdigit():
            raise SystemExit("ISSUE_ID must be numeric")
        patch_script = None
        message = None
        if ns.finalize_message is not None:
            raise SystemExit(
                "finalize-workspace mode must not use -f/--finalize-live; "
                "commit message is read from workspace meta.json"
            )
        if ns.rest:
            raise SystemExit("finalize-workspace mode must not include positional args")
    elif ns.finalize_message is not None:
        mode = "finalize"
        issue_id = None
        patch_script = None
        message = ns.finalize_message
        if ns.rest:
            raise SystemExit("finalize mode (-f/--finalize-live) must not include positional args")
    else:
        mode = "workspace"
        if len(ns.rest) < 2:
            raise SystemExit("workspace mode requires: ISSUE_ID MESSAGE [PATCH_SCRIPT]")
        issue_id = ns.rest[0]
        if not str(issue_id).isdigit():
            raise SystemExit("ISSUE_ID must be numeric")
        message = ns.rest[1]
        patch_script = ns.rest[2] if len(ns.rest) >= 3 else None

    return CliArgs(
        mode=mode,
        issue_id=issue_id,
        patch_script=patch_script,
        message=message,
        run_all_tests=ns.run_all_tests,
        allow_no_op=ns.allow_no_op,
        unified_patch=getattr(ns, "unified_patch", None),
        patch_strip=getattr(ns, "patch_strip", None),
        skip_up_to_date=ns.skip_up_to_date,
        allow_non_main=ns.allow_non_main,
        no_rollback=ns.no_rollback,
        update_workspace=ns.update_workspace,
        soft_reset_workspace=ns.soft_reset_workspace,
        enforce_allowed_files=ns.enforce_allowed_files,
        rollback_workspace_on_fail=ns.rollback_workspace_on_fail,
        live_repo_guard=ns.live_repo_guard,
        live_repo_guard_scope=ns.live_repo_guard_scope,
        patch_jail=ns.patch_jail,
        patch_jail_unshare_net=ns.patch_jail_unshare_net,
        ruff_format=ns.ruff_format,
        pytest_use_venv=ns.pytest_use_venv,
        overrides=ns.overrides,
        require_push_success=ns.require_push_success,
        allow_outside_files=ns.allow_outside_files,
        allow_declared_untouched=ns.allow_declared_untouched,
        disable_promotion=ns.disable_promotion,
        allow_live_changed=ns.allow_live_changed,
        allow_gates_fail=ns.allow_gates_fail,
        skip_ruff=ns.skip_ruff,
        skip_pytest=ns.skip_pytest,
        skip_mypy=ns.skip_mypy,
        gates_order=ns.gates_order,
        ruff_autofix_legalize_outside=ns.ruff_autofix_legalize_outside,
        load_latest_patch=ns.load_latest_patch,
        keep_workspace=ns.keep_workspace,
        test_mode=ns.test_mode,
        post_success_audit=ns.post_success_audit,
    )
