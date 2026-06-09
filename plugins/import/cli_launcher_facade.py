"""CLI launcher facade for import plugin.

This module centralizes root/path resolution and validation so that the
renderer file does not accumulate cross-area imports.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeGuard

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .dsl.default_wizard_v3 import build_default_wizard_definition_v3
from .engine_session_guards import validate_root_and_path
from .fingerprints import fingerprint_json
from .storage import read_json
from .wizard_definition_model import (
    WIZARD_DEFINITION_REL_PATH,
    canonicalize_wizard_definition,
)


class _LauncherConfig(Protocol):
    @property
    def launcher_mode(self) -> str: ...

    @property
    def default_root(self) -> str: ...

    @property
    def default_path(self) -> str: ...

    @property
    def noninteractive(self) -> bool: ...

    @property
    def confirm_defaults(self) -> bool: ...

    @property
    def nav_ui(self) -> str: ...


class _SupportsStartProcessing(Protocol):
    def start_processing(self, session_id: str, body: dict[str, object]) -> dict[str, object]: ...


class _SupportsWizardDefinitionRuntime(Protocol):
    def get_file_service(self) -> FileService: ...

    def delete_path(self, root: RootName, relative_path: str, *, missing_ok: bool) -> None: ...


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _wizard_definition_fingerprint(wizard_definition: object) -> str:
    canonical = canonicalize_wizard_definition(wizard_definition)
    return fingerprint_json(canonical)


def runtime_wizard_definition_matches_default(
    engine: _SupportsWizardDefinitionRuntime,
) -> bool:
    fs = engine.get_file_service()
    if not fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH):
        return True

    default_fp = _wizard_definition_fingerprint(build_default_wizard_definition_v3())
    try:
        runtime_any = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
        runtime_fp = _wizard_definition_fingerprint(runtime_any)
    except Exception:
        return False
    return runtime_fp == default_fp


def prompt_delete_runtime_wizard_definition(
    *,
    engine: _SupportsWizardDefinitionRuntime,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> bool:
    if runtime_wizard_definition_matches_default(engine):
        return True

    raw = (
        input_fn(
            "Runtime wizard_definition.json differs from shipped default. "
            "Delete runtime and regenerate the shipped default? (y/n): "
        )
        .strip()
        .lower()
    )
    if raw not in {"y", "yes", "1", "true", "t"}:
        return True

    engine.delete_path(RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, missing_ok=True)
    print_fn("Runtime wizard_definition.json deleted.")
    return True


def resolve_launcher_inputs(
    *,
    engine: object,
    cfg: _LauncherConfig,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> tuple[bool, str, str, str]:
    """Resolve (root, relative_path) for the launcher.

    Rules:
    - noninteractive has absolute priority
    - noninteractive must never prompt
    - root is required
    - relative_path may be "" (default)
    """

    launcher_mode = str(cfg.launcher_mode or "interactive")
    default_root = str(cfg.default_root or "")
    default_path = str(cfg.default_path or "")
    noninteractive = bool(cfg.noninteractive)

    if noninteractive:
        root = default_root
        rel_path = default_path
        if not str(root or "").strip():
            return False, "", "", "ERROR: noninteractive requires root"
        v = validate_root_and_path(root, rel_path)
        if isinstance(v, dict):
            return False, "", "", "ERROR: invalid root/path"
        root_n, rel_n = v
        return True, root_n, rel_n, ""

    if launcher_mode == "fixed":
        v = validate_root_and_path(default_root, default_path)
        if isinstance(v, dict):
            return False, "", "", "ERROR: invalid root/path"
        root_n, rel_n = v
        return True, root_n, rel_n, ""

    # interactive
    if bool(cfg.confirm_defaults):
        v = validate_root_and_path(default_root, default_path)
        if not isinstance(v, dict):
            root_n, rel_n = v
            return True, root_n, rel_n, ""

    picked_root = _pick_root(cfg, input_fn=input_fn, print_fn=print_fn)
    if picked_root is None:
        return False, "", "", "ERROR: canceled"
    picked_rel_path = _pick_path(
        engine,
        cfg,
        root=picked_root,
        input_fn=input_fn,
        print_fn=print_fn,
    )
    if picked_rel_path is None:
        return False, "", "", "ERROR: canceled"

    v = validate_root_and_path(picked_root, picked_rel_path)
    if isinstance(v, dict):
        return False, "", "", "ERROR: invalid root/path"
    root_n, rel_n = v
    return True, root_n, rel_n, ""


def _pick_root(
    cfg: _LauncherConfig,
    *,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str | None:
    roots = [r.value for r in RootName]
    default_root = str(cfg.default_root or "")
    default = default_root if default_root in roots else "inbox"

    confirm_defaults = bool(cfg.confirm_defaults)

    print_fn("Select root:")
    for idx, r in enumerate(roots, start=1):
        mark = " *" if r == default else ""
        print_fn(f"  {idx}. {r}{mark}")

    if not confirm_defaults:
        prompt = "Enter root number: "
    else:
        prompt = "Enter root number (Enter=default): "

    raw = input_fn(prompt).strip()
    nav_ui = str(cfg.nav_ui or "prompt")
    if nav_ui in {"inline", "both"} and raw.strip().lower() in {":cancel", "cancel"}:
        return None
    if raw == "" and confirm_defaults:
        return default
    try:
        n = int(raw)
        if 1 <= n <= len(roots):
            return roots[n - 1]
    except Exception:
        pass
    print_fn("Invalid selection, using default.")
    return default


def _pick_path(
    engine: object,
    cfg: _LauncherConfig,
    *,
    root: str,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str | None:
    del engine
    del root

    default = str(cfg.default_path or "")
    confirm_defaults = bool(cfg.confirm_defaults)

    print_fn("Path is relative to the selected root. Leave empty for root.")

    if not confirm_defaults:
        prompt = "Enter path (relative): "
    else:
        prompt = "Enter path (relative) (Enter=default): "

    raw = input_fn(prompt).strip()
    nav_ui = str(cfg.nav_ui or "prompt")
    if nav_ui in {"inline", "both"} and raw.strip().lower() in {":cancel", "cancel"}:
        return None
    if raw == "" and confirm_defaults:
        return default
    return raw


def begin_phase2(
    engine: _SupportsStartProcessing,
    session_id: str,
    *,
    print_fn: Callable[[str], None],
) -> int:
    """Start PHASE 2 processing (confirm=true) and print result.

    Renderer must not branch on step_id; this facade is allowed to call engine APIs.
    """
    result = engine.start_processing(session_id, {"confirm": True})

    job_ids_any = result.get("job_ids")
    batch_size_any = result.get("batch_size")

    if _is_object_list(job_ids_any):
        print_fn("job_ids: " + ", ".join(str(job_id) for job_id in job_ids_any))
    if isinstance(batch_size_any, int) and not isinstance(batch_size_any, bool):
        print_fn(f"batch_size: {batch_size_any}")

    print_fn(_json_dump(result))
    if "error" in result:
        return 1
    return 0


def _json_dump(obj: object) -> str:
    import json

    return json.dumps(obj, indent=2, sort_keys=True)


def prompt_session_start_intent(
    *,
    session_id: str,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str | None:
    print_fn(f"Existing session detected: {session_id}")
    print_fn("Choose start intent:")
    print_fn("  1. Resume existing session")
    print_fn("  2. Start new session")
    print_fn("  3. Cancel")
    raw = input_fn("Enter choice (1/2/3): ").strip().lower()
    if raw in {"1", "r", "resume"}:
        return "resume"
    if raw in {"2", "n", "new"}:
        return "new"
    return None
