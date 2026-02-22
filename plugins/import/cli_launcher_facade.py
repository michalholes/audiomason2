"""CLI launcher facade for import plugin.

This module centralizes root/path resolution and validation so that the
renderer file does not accumulate cross-area imports.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plugins.file_io.service.types import RootName

from .engine_session_guards import validate_root_and_path


def resolve_launcher_inputs(
    *,
    engine: Any,
    cfg: Any,
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

    launcher_mode = str(getattr(cfg, "launcher_mode", "interactive"))
    default_root = str(getattr(cfg, "default_root", ""))
    default_path = str(getattr(cfg, "default_path", ""))
    noninteractive = bool(getattr(cfg, "noninteractive", False))

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
    cfg: Any,
    *,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str | None:
    roots = [r.value for r in RootName]
    default_root = str(getattr(cfg, "default_root", ""))
    default = default_root if default_root in roots else "inbox"

    confirm_defaults = bool(getattr(cfg, "confirm_defaults", True))

    print_fn("Select root:")
    for idx, r in enumerate(roots, start=1):
        mark = " *" if r == default else ""
        print_fn(f"  {idx}. {r}{mark}")

    if not confirm_defaults:
        prompt = "Enter root number: "
    else:
        prompt = "Enter root number (Enter=default): "

    raw = input_fn(prompt).strip()
    nav_ui = str(getattr(cfg, "nav_ui", "prompt"))
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
    engine: Any,
    cfg: Any,
    *,
    root: str,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str | None:
    default = str(getattr(cfg, "default_path", ""))

    try:
        root_enum = RootName(str(root or "").strip())
    except Exception:
        return default

    fs = engine.get_file_service()

    # Offer a shallow directory picker (root-level only).
    try:
        entries = fs.list_dir(root_enum, ".", recursive=False)
    except Exception:
        entries = []

    dirs = sorted(
        [
            e.rel_path
            for e in entries
            if getattr(e, "is_dir", False) and isinstance(getattr(e, "rel_path", None), str)
        ]
    )

    max_list_items = int(getattr(cfg, "max_list_items", 200) or 200)
    if max_list_items < 1:
        max_list_items = 1

    if dirs and len(dirs) > max_list_items:
        dirs = dirs[:max_list_items]

    confirm_defaults = bool(getattr(cfg, "confirm_defaults", True))

    print_fn("Select path (relative):")
    print_fn(f"  0. (root) {'*' if default in {'', '.'} else ''}")
    for idx, d in enumerate(dirs, start=1):
        mark = " *" if d == default else ""
        print_fn(f"  {idx}. {d}{mark}")

    if not confirm_defaults:
        prompt = "Enter path number (or custom path): "
    else:
        prompt = "Enter path number (Enter=default): "

    raw = input_fn(prompt).strip()
    nav_ui = str(getattr(cfg, "nav_ui", "prompt"))
    if nav_ui in {"inline", "both"} and raw.strip().lower() in {":cancel", "cancel"}:
        return None
    if raw == "" and confirm_defaults:
        return default

    try:
        n = int(raw)
        if n == 0:
            return ""
        if 1 <= n <= len(dirs):
            return dirs[n - 1]
    except Exception:
        # Treat as custom path
        return raw

    print_fn("Invalid selection, using default.")
    return default


def begin_phase2(engine: Any, session_id: str, *, print_fn: Callable[[str], None]) -> int:
    """Start PHASE 2 processing (confirm=true) and print result.

    Renderer must not branch on step_id; this facade is allowed to call engine APIs.
    """
    result = engine.start_processing(session_id, {"confirm": True})

    job_ids = result.get("job_ids") if isinstance(result, dict) else None
    batch_size = result.get("batch_size") if isinstance(result, dict) else None

    if isinstance(job_ids, list):
        print_fn("job_ids: " + ", ".join(str(x) for x in job_ids))
    if isinstance(batch_size, int):
        print_fn(f"batch_size: {batch_size}")

    print_fn(_json_dump(result))
    if isinstance(result, dict) and "error" in result:
        return 1
    return 0


def _json_dump(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, sort_keys=True)
