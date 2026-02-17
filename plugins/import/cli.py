"""Import plugin CLI adapter.

Implements:
  audiomason import wizard <subcommand> ...

This is UI-only: it delegates all validation and state transitions to the
ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

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

    wiz_sub.add_parser("help", add_help=False)
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


def import_cli_main(argv: list[str], *, engine: ImportWizardEngine) -> int:
    parser = _build_parser()

    if not argv:
        _print_help()
        return 0

    try:
        ns = parser.parse_args(argv)
    except SystemExit:
        _print_help()
        raise SystemExit(1) from None

    if ns.cmd != "wizard":
        _print_help()
        raise SystemExit(1)

    if ns.wiz_cmd in (None, "help"):
        _print_help()
        return 0

    try:
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
