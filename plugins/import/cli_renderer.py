"""Interactive CLI renderer for Import Wizard.

This is UI-only: it renders steps, collects inputs, and delegates all
validation and transitions to ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from audiomason.core.config import ConfigResolver
from plugins.file_io.service import RootName

from .engine import ImportWizardEngine
from .storage import read_json


@dataclass(frozen=True)
class RendererConfig:
    launcher_mode: str
    default_root: str
    default_path: str
    noninteractive: bool
    confirm_defaults: bool
    show_internal_ids: bool
    max_list_items: int


def _cfg_get(resolver: ConfigResolver, key: str, default: Any) -> Any:
    try:
        value, _source = resolver.resolve(key)
        return value
    except Exception:
        return default


def load_renderer_config(resolver: ConfigResolver) -> RendererConfig:
    launcher_mode = str(_cfg_get(resolver, "plugins.import.cli.launcher_mode", "interactive"))
    default_root = str(_cfg_get(resolver, "plugins.import.cli.default_root", "inbox"))
    default_path = str(_cfg_get(resolver, "plugins.import.cli.default_path", ""))

    noninteractive = bool(_cfg_get(resolver, "plugins.import.cli.noninteractive", False))
    confirm_defaults = bool(_cfg_get(resolver, "plugins.import.cli.render.confirm_defaults", True))
    show_internal_ids = bool(
        _cfg_get(resolver, "plugins.import.cli.render.show_internal_ids", False)
    )
    max_list_items_any = _cfg_get(resolver, "plugins.import.cli.render.max_list_items", 200)
    try:
        max_list_items = int(max_list_items_any)
    except Exception:
        max_list_items = 200

    if max_list_items < 1:
        max_list_items = 1
    if max_list_items > 5000:
        max_list_items = 5000

    if launcher_mode not in {"interactive", "fixed", "disabled"}:
        launcher_mode = "interactive"

    return RendererConfig(
        launcher_mode=launcher_mode,
        default_root=default_root,
        default_path=default_path,
        noninteractive=noninteractive,
        confirm_defaults=confirm_defaults,
        show_internal_ids=show_internal_ids,
        max_list_items=max_list_items,
    )


def run_launcher(
    *,
    engine: ImportWizardEngine,
    resolver: ConfigResolver,
    cli_overrides: dict[str, Any],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> int:
    cfg = load_renderer_config(resolver)
    cfg = _apply_overrides(cfg, cli_overrides)

    if cfg.launcher_mode == "disabled":
        return 0

    if cfg.launcher_mode == "fixed":
        root = cfg.default_root
        rel_path = cfg.default_path
    else:
        root = _pick_root(cfg, input_fn=input_fn, print_fn=print_fn)
        rel_path = _pick_path(engine, cfg, root=root, input_fn=input_fn, print_fn=print_fn)

    # Validate root/path early (engine will validate too, but keep errors user-friendly).
    try:
        RootName(root)
    except Exception:
        print_fn(f"ERROR: invalid root: {root}")
        return 1
    if ".." in [seg for seg in str(rel_path).replace("\\", "/").split("/") if seg]:
        print_fn("ERROR: invalid path: '..' is forbidden")
        return 1

    if cfg.noninteractive and (cfg.launcher_mode == "interactive"):
        # If noninteractive is forced, we must not prompt further. Root/path were chosen above.
        # This is acceptable because those prompts happened already; keep behavior strict.
        pass

    state = engine.create_session(root, rel_path)
    session_id = str(state.get("session_id") or "")
    if not session_id:
        # Engine returns error envelope.
        print_fn(_json_dump({"state": state}))
        return 1

    return _render_loop(
        engine=engine,
        cfg=cfg,
        session_id=session_id,
        input_fn=input_fn,
        print_fn=print_fn,
    )


def _apply_overrides(cfg: RendererConfig, overrides: dict[str, Any]) -> RendererConfig:
    launcher_mode = str(overrides.get("launcher_mode", cfg.launcher_mode))
    if launcher_mode not in {"interactive", "fixed", "disabled"}:
        launcher_mode = cfg.launcher_mode

    default_root = str(overrides.get("root", cfg.default_root))
    default_path = str(overrides.get("path", cfg.default_path))

    noninteractive = bool(overrides.get("noninteractive", cfg.noninteractive))
    confirm_defaults = bool(overrides.get("confirm_defaults", cfg.confirm_defaults))
    show_internal_ids = bool(overrides.get("show_internal_ids", cfg.show_internal_ids))

    max_list_items = cfg.max_list_items
    if "max_list_items" in overrides:
        try:
            max_list_items = int(overrides["max_list_items"])
        except Exception:
            max_list_items = cfg.max_list_items

    if max_list_items < 1:
        max_list_items = 1
    if max_list_items > 5000:
        max_list_items = 5000

    return RendererConfig(
        launcher_mode=launcher_mode,
        default_root=default_root,
        default_path=default_path,
        noninteractive=noninteractive,
        confirm_defaults=confirm_defaults,
        show_internal_ids=show_internal_ids,
        max_list_items=max_list_items,
    )


def _pick_root(
    cfg: RendererConfig,
    *,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str:
    roots = [r.value for r in RootName]
    default = cfg.default_root if cfg.default_root in roots else "inbox"

    if cfg.noninteractive:
        return default

    print_fn("Select root:")
    for idx, r in enumerate(roots, start=1):
        mark = " *" if r == default else ""
        print_fn(f"  {idx}. {r}{mark}")

    if not cfg.confirm_defaults:
        prompt = "Enter root number: "
    else:
        prompt = "Enter root number (Enter=default): "

    raw = input_fn(prompt).strip()
    if raw == "" and cfg.confirm_defaults:
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
    engine: ImportWizardEngine,
    cfg: RendererConfig,
    *,
    root: str,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> str:
    default = cfg.default_path

    if cfg.noninteractive:
        return default

    fs = engine.get_file_service()
    try:
        root_enum = RootName(root)
    except Exception:
        return default

    # Offer a shallow directory picker (root-level only).
    try:
        entries = fs.list_dir(root_enum, ".", recursive=False)
    except Exception:
        entries = []

    dirs = [e for e in entries if getattr(e, "is_dir", False)]
    dirs_sorted = sorted(dirs, key=lambda e: str(getattr(e, "rel_path", "")))

    if not dirs_sorted:
        if cfg.confirm_defaults:
            raw = input_fn(f"Relative path in {root} (Enter=default '{default}'): ").strip()
            return raw if raw != "" else default
        return input_fn(f"Relative path in {root}: ").strip()

    print_fn(f"Select directory under root '{root}':")
    print_fn("  0. (none)")
    for idx, e in enumerate(dirs_sorted[: cfg.max_list_items], start=1):
        rel = str(getattr(e, "rel_path", ""))
        print_fn(f"  {idx}. {rel}/")

    if cfg.confirm_defaults:
        prompt = f"Enter number (Enter=default '{default or '(none)'}'): "
    else:
        prompt = "Enter number: "
    raw = input_fn(prompt).strip()
    if raw == "" and cfg.confirm_defaults:
        return default
    try:
        n = int(raw)
        if n == 0:
            return ""
        if 1 <= n <= min(len(dirs_sorted), cfg.max_list_items):
            return str(getattr(dirs_sorted[n - 1], "rel_path", ""))
    except Exception:
        pass

    print_fn("Invalid selection, using default.")
    return default


def _render_loop(
    *,
    engine: ImportWizardEngine,
    cfg: RendererConfig,
    session_id: str,
    input_fn: Callable[[str], str],
    print_fn: Callable[[str], None],
) -> int:
    while True:
        state = engine.get_state(session_id)
        cur = str(state.get("current_step_id") or "")
        if not cur:
            print_fn(_json_dump({"state": state}))
            return 1

        step = engine.get_step_definition(session_id, cur)
        if "error" in step:
            print_fn(_json_dump({"step": step}))
            return 1

        title = str(step.get("title") or cur)
        if cfg.show_internal_ids:
            print_fn(f"Step: {title} [{cur}]")
        else:
            print_fn(f"Step: {title}")

        computed_only = bool(step.get("computed_only"))
        fields_any = step.get("fields")
        fields: list[dict[str, Any]] = (
            [f for f in fields_any if isinstance(f, dict)] if isinstance(fields_any, list) else []
        )

        if computed_only or not fields:
            # No user input required; advance.
            state2 = engine.apply_action(session_id, "next")
            if state2.get("status") in {"done", "aborted"}:
                return _finalize(engine, session_id, print_fn=print_fn)
            continue

        if cfg.noninteractive:
            print_fn("ERROR: noninteractive mode requires explicit wizard step payloads.")
            return 1

        payload: dict[str, Any] = {}
        for f in fields:
            name = f.get("name")
            ftype = f.get("type")
            if not isinstance(name, str) or not isinstance(ftype, str):
                continue

            if ftype == "multi_select_indexed":
                _show_select_items(engine, session_id, name=name, cfg=cfg, print_fn=print_fn)
                expr = input_fn(f"{name} selection (e.g. all, 1,3,5-8): ").strip()
                payload[f"{name}_expr"] = expr
                continue

            if ftype in {"toggle", "confirm"}:
                raw = input_fn(f"{name} (y/n): ").strip().lower()
                payload[name] = raw in {"y", "yes", "1", "true", "t"}
                continue

            if ftype == "number":
                raw = input_fn(f"{name} (int): ").strip()
                try:
                    payload[name] = int(raw)
                except Exception:
                    payload[name] = raw
                continue

            if ftype in {"text", "select"}:
                payload[name] = input_fn(f"{name}: ").rstrip("\n")
                continue

            # Fallback: ask for raw JSON value.
            raw = input_fn(f"{name} (raw): ").rstrip("\n")
            payload[name] = raw

        state3 = engine.submit_step(session_id, cur, payload)
        if state3.get("status") in {"done", "aborted"}:
            return _finalize(engine, session_id, print_fn=print_fn)

        # Simple navigation prompt.
        nav = input_fn("Action (:next, :back, :cancel, Enter=continue): ").strip().lower()
        if nav in {":next", "next"}:
            engine.apply_action(session_id, "next")
        elif nav in {":back", "back"}:
            engine.apply_action(session_id, "back")
        elif nav in {":cancel", "cancel"}:
            engine.apply_action(session_id, "cancel")
            return 1

        # Loop continues and re-renders current state.
        continue


def _show_select_items(
    engine: ImportWizardEngine,
    session_id: str,
    *,
    name: str,
    cfg: RendererConfig,
    print_fn: Callable[[str], None],
) -> None:
    # Best-effort display: show discovery items (ordered) if present.
    fs = engine.get_file_service()
    session_dir = f"import/sessions/{session_id}"
    try:
        discovery_any = read_json(fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
    except Exception:
        return
    if not (isinstance(discovery_any, list) and all(isinstance(x, dict) for x in discovery_any)):
        return

    items: list[dict[str, Any]] = [dict(x) for x in discovery_any]
    if not items:
        return

    print_fn(f"Selectable items for '{name}':")
    for idx, it in enumerate(items[: cfg.max_list_items], start=1):
        rel = str(it.get("relative_path") or "")
        kind = str(it.get("kind") or "")
        print_fn(f"  {idx}. {rel} ({kind})")
    if len(items) > cfg.max_list_items:
        print_fn(f"  ... ({len(items) - cfg.max_list_items} more)")


def _finalize(
    engine: ImportWizardEngine, session_id: str, *, print_fn: Callable[[str], None]
) -> int:
    result = engine.finalize(session_id)
    print_fn(_json_dump(result))
    if isinstance(result, dict) and "error" in result:
        return 1
    return 0


def _json_dump(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, sort_keys=True)
