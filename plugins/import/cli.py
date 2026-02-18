"""Import plugin CLI adapter.

Implements:
  audiomason import
  audiomason import wizard <subcommand> ...
  audiomason import editor ...

This is UI-only: it delegates all validation and state transitions to the
ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from audiomason.core.config import ConfigResolver

from .cli_renderer import load_renderer_config, run_launcher
from .editor import (
    edit_catalog_interactive,
    edit_flow_interactive,
    preview_effective_model,
    save_catalog_validated,
    save_flow_validated,
    show_catalog,
    show_flow,
    validate_catalog,
    validate_flow,
)
from .engine import ImportWizardEngine
from .errors import ImportWizardError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audiomason import", add_help=False)
    sub = p.add_subparsers(dest="cmd")

    wiz = sub.add_parser("wizard", add_help=False)
    wiz_sub = wiz.add_subparsers(dest="wiz_cmd")

    start = wiz_sub.add_parser("start", add_help=False)
    start.add_argument("--root", required=True)
    start.add_argument("--path", required=True)

    resume = wiz_sub.add_parser("resume", add_help=False)
    resume.add_argument("session_id")

    state = wiz_sub.add_parser("state", add_help=False)
    state.add_argument("session_id")

    step = wiz_sub.add_parser("step", add_help=False)
    step.add_argument("session_id")
    step.add_argument("step_id")
    step.add_argument("--json", required=True, dest="payload_json")

    plan = wiz_sub.add_parser("plan", add_help=False)
    plan.add_argument("session_id")

    finalize = wiz_sub.add_parser("finalize", add_help=False)
    finalize.add_argument("session_id")

    ed = sub.add_parser("editor", add_help=False)
    ed_sub = ed.add_subparsers(dest="ed_area")

    cat = ed_sub.add_parser("catalog", add_help=False)
    cat_sub = cat.add_subparsers(dest="ed_cmd")
    cat_sub.add_parser("show", add_help=False)
    cat_sub.add_parser("edit", add_help=False)
    cat_sub.add_parser("validate", add_help=False)
    cat_sub.add_parser("save", add_help=False)

    fl = ed_sub.add_parser("flow", add_help=False)
    fl_sub = fl.add_subparsers(dest="ed_cmd")
    fl_sub.add_parser("show", add_help=False)
    fl_sub.add_parser("edit", add_help=False)
    fl_sub.add_parser("validate", add_help=False)
    fl_sub.add_parser("save", add_help=False)

    em = ed_sub.add_parser("effective-model", add_help=False)
    em_sub = em.add_subparsers(dest="ed_cmd")
    em_sub.add_parser("preview", add_help=False)

    wiz_sub.add_parser("help", add_help=False)
    return p


def _build_launcher_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="audiomason import", add_help=False)
    p.add_argument(
        "--launcher",
        choices=["interactive", "fixed", "disabled"],
        dest="launcher_mode",
        default=None,
    )
    p.add_argument("--no-launcher", action="store_true", default=False)
    p.add_argument("--root", dest="root", default=None)
    p.add_argument("--path", dest="path", default=None)
    p.add_argument("--noninteractive", action="store_true", default=False)
    p.add_argument("--max-list-items", dest="max_list_items", default=None)
    p.add_argument("--show-ids", action="store_true", default=False)
    p.add_argument("--confirm-defaults", action="store_true", default=False)
    p.add_argument("--no-confirm-defaults", action="store_true", default=False)
    return p


def _print_help() -> None:
    print("Usage:")
    print("  audiomason import wizard start --root <root> --path <relative_path>")
    print("  audiomason import wizard resume <session_id>")
    print("  audiomason import wizard state <session_id>")
    print("  audiomason import wizard step <session_id> <step_id> --json <payload>")
    print("  audiomason import wizard plan <session_id>")
    print("  audiomason import wizard finalize <session_id>")
    print("  audiomason import wizard help")
    print("")
    print("  audiomason import editor catalog show")
    print("  audiomason import editor catalog edit")
    print("  audiomason import editor catalog validate")
    print("  audiomason import editor catalog save")
    print("  audiomason import editor flow show")
    print("  audiomason import editor flow edit")
    print("  audiomason import editor flow validate")
    print("  audiomason import editor flow save")
    print("  audiomason import editor effective-model preview")
    print("")
    print("Launcher (CLI renderer):")
    print("  audiomason import [--root <root>] [--path <rel>] [--launcher <mode>]")
    print("  audiomason import --no-launcher")
    print("  audiomason import --noninteractive --root <root> --path <rel>")


def _error_envelope(
    *, code: str, message_id: str, default_message: str, details: Any
) -> dict[str, Any]:
    return {
        "code": code,
        "message_id": message_id,
        "default_message": default_message,
        "details": details,
    }


def _dump(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _current_prompt(engine: ImportWizardEngine, session_id: str) -> dict[str, Any]:
    state = engine.get_state(session_id)
    step_id = str(state.get("current_step_id") or "")
    step_def = engine.get_step_definition(session_id, step_id) if step_id else None
    return {
        "current_step_id": step_id,
        "step": step_def,
    }


def import_cli_main(
    argv: list[str], *, engine: ImportWizardEngine, resolver: ConfigResolver
) -> int:
    # If the user invoked explicit subcommands, preserve legacy behavior.
    if argv and argv[0] in {"wizard", "editor"}:
        return _run_legacy(argv, engine=engine)

    # Otherwise, parse launcher flags (if any) and decide whether to run the
    # interactive CLI renderer or show help.
    launcher_parser = _build_launcher_parser()
    try:
        ns, rest = launcher_parser.parse_known_args(argv)
    except SystemExit:
        _print_help()
        raise SystemExit(1) from None

    if rest and rest[0] in {"wizard", "editor"}:
        # User mixed launcher flags with explicit subcommands. Let legacy parser handle it.
        return _run_legacy(argv, engine=engine)

    cli_overrides: dict[str, Any] = {}
    if ns.no_launcher:
        cli_overrides["launcher_mode"] = "disabled"
    elif ns.launcher_mode:
        cli_overrides["launcher_mode"] = ns.launcher_mode

    if ns.root is not None:
        cli_overrides["root"] = ns.root
    if ns.path is not None:
        cli_overrides["path"] = ns.path

    if ns.noninteractive:
        cli_overrides["noninteractive"] = True

    if ns.max_list_items is not None:
        cli_overrides["max_list_items"] = ns.max_list_items

    if ns.show_ids:
        cli_overrides["show_internal_ids"] = True

    if ns.confirm_defaults and ns.no_confirm_defaults:
        _print_help()
        raise SystemExit(1)

    if ns.confirm_defaults:
        cli_overrides["confirm_defaults"] = True
    if ns.no_confirm_defaults:
        cli_overrides["confirm_defaults"] = False

    cfg = load_renderer_config(resolver)
    effective_launcher_mode = str(cli_overrides.get("launcher_mode", cfg.launcher_mode))
    if effective_launcher_mode == "disabled":
        _print_help()
        return 0

    return run_launcher(
        engine=engine,
        resolver=resolver,
        cli_overrides=cli_overrides,
    )


def _run_legacy(argv: list[str], *, engine: ImportWizardEngine) -> int:
    parser = _build_parser()

    if not argv:
        _print_help()
        return 0

    try:
        ns = parser.parse_args(argv)
    except SystemExit:
        _print_help()
        raise SystemExit(1) from None

    if ns.cmd not in ("wizard", "editor"):
        _print_help()
        raise SystemExit(1)

    if ns.cmd == "wizard" and ns.wiz_cmd in (None, "help"):
        _print_help()
        return 0

    try:
        if ns.cmd == "editor":
            if ns.ed_area is None or ns.ed_cmd is None:
                _print_help()
                return 0

            if ns.ed_area == "catalog":
                if ns.ed_cmd == "show":
                    res = show_catalog(engine)
                    _dump(res.data)
                    return 0
                if ns.ed_cmd == "validate":
                    res = validate_catalog(engine)
                    _dump(res.data)
                    if not res.ok:
                        raise SystemExit(1) from None
                    return 0
                if ns.ed_cmd == "save":
                    res = save_catalog_validated(engine)
                    _dump(res.data)
                    if not res.ok:
                        raise SystemExit(1) from None
                    return 0
                if ns.ed_cmd == "edit":
                    res = edit_catalog_interactive(engine)
                    _dump(res.data)
                    if not res.ok:
                        raise SystemExit(1) from None
                    return 0

            if ns.ed_area == "flow":
                if ns.ed_cmd == "show":
                    res = show_flow(engine)
                    _dump(res.data)
                    return 0
                if ns.ed_cmd == "validate":
                    res = validate_flow(engine)
                    _dump(res.data)
                    if not res.ok:
                        raise SystemExit(1) from None
                    return 0
                if ns.ed_cmd == "save":
                    res = save_flow_validated(engine)
                    _dump(res.data)
                    if not res.ok:
                        raise SystemExit(1) from None
                    return 0
                if ns.ed_cmd == "edit":
                    res = edit_flow_interactive(engine)
                    _dump(res.data)
                    if not res.ok:
                        raise SystemExit(1) from None
                    return 0

            if ns.ed_area == "effective-model" and ns.ed_cmd == "preview":
                res = preview_effective_model(engine)
                _dump(res.data)
                if not res.ok:
                    raise SystemExit(1) from None
                return 0

            _print_help()
            raise SystemExit(1)

        if ns.wiz_cmd == "start":
            state = engine.create_session(ns.root, ns.path)
            out = {
                "session_id": state.get("session_id"),
                "state": state,
                "prompt": _current_prompt(engine, str(state.get("session_id"))),
            }
            _dump(out)
            return 0

        if ns.wiz_cmd == "resume":
            state = engine.get_state(ns.session_id)
            out = {
                "session_id": ns.session_id,
                "state": state,
                "prompt": _current_prompt(engine, ns.session_id),
            }
            _dump(out)
            return 0

        if ns.wiz_cmd == "state":
            state = engine.get_state(ns.session_id)
            _dump(state)
            return 0

        if ns.wiz_cmd == "step":
            try:
                payload = json.loads(ns.payload_json)
            except Exception as e:
                env = _error_envelope(
                    code="invalid_json",
                    message_id="cli.invalid_json",
                    default_message="payload is not valid JSON",
                    details={"error": str(e)},
                )
                _dump(env)
                raise SystemExit(1) from None
            if not isinstance(payload, dict):
                env = _error_envelope(
                    code="invalid_payload",
                    message_id="cli.payload_not_object",
                    default_message="payload must be a JSON object",
                    details={"type": type(payload).__name__},
                )
                _dump(env)
                raise SystemExit(1)

            state = engine.submit_step(ns.session_id, ns.step_id, payload)
            out = {
                "session_id": ns.session_id,
                "state": state,
                "prompt": _current_prompt(engine, ns.session_id),
            }
            _dump(out)
            return 0

        if ns.wiz_cmd == "plan":
            plan = engine.compute_plan(ns.session_id)
            _dump(plan)
            return 0

        if ns.wiz_cmd == "finalize":
            result = engine.finalize(ns.session_id)
            _dump(result)
            return 0

        _print_help()
        raise SystemExit(1)

    except FileNotFoundError as e:
        missing_path = getattr(e, "filename", None) or str(e)
        if ns.wiz_cmd in ("start", "resume"):
            env = _error_envelope(
                code="missing_wizard_model",
                message_id="cli.import.missing_wizard_model",
                default_message=(
                    "Missing Import Wizard model files under the wizards root. "
                    "Create catalog/catalog.json and flow/current.json."
                ),
                details={
                    "missing_path": missing_path,
                    "expected_rel_paths": [
                        "import/catalog/catalog.json",
                        "import/flow/current.json",
                    ],
                },
            )
            _dump(env)
            raise SystemExit(1) from None

        env = _error_envelope(
            code="unexpected_error",
            message_id="cli.unexpected_error",
            default_message=str(e) or e.__class__.__name__,
            details={"type": e.__class__.__name__},
        )
        _dump(env)
        raise SystemExit(1) from None

    except ImportWizardError as e:
        env = _error_envelope(
            code=e.__class__.__name__,
            message_id=f"import.{e.__class__.__name__}",
            default_message=str(e) or e.__class__.__name__,
            details={"type": e.__class__.__name__},
        )
        _dump(env)
        raise SystemExit(1) from None
    except Exception as e:
        env = _error_envelope(
            code="unexpected_error",
            message_id="cli.unexpected_error",
            default_message=str(e) or e.__class__.__name__,
            details={"type": e.__class__.__name__},
        )
        _dump(env)
        raise SystemExit(1) from None
