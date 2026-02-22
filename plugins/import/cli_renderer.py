"""Interactive CLI renderer for Import Wizard.

This is UI-only: it renders steps, collects inputs, and delegates all
validation and transitions to ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .cli_launcher_facade import begin_phase2, resolve_launcher_inputs
from .engine import ImportWizardEngine


@dataclass(frozen=True)
class RendererConfig:
    launcher_mode: str
    default_root: str
    default_path: str
    noninteractive: bool
    confirm_defaults: bool
    show_internal_ids: bool
    max_list_items: int
    nav_ui: str


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True)


def _cfg_get(resolver: Any, key: str, default: Any) -> Any:
    try:
        value, _source = resolver.resolve(key)
        return value
    except Exception:
        return default


def load_renderer_config(resolver: Any) -> RendererConfig:
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

    nav_ui_raw = str(_cfg_get(resolver, "plugins.import.cli.render.nav_ui", "prompt"))
    nav_ui = nav_ui_raw.strip().lower() or "prompt"
    if nav_ui not in {"prompt", "inline", "both"}:
        nav_ui = "prompt"

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
        nav_ui=nav_ui,
    )


def run_launcher(
    *,
    engine: ImportWizardEngine,
    resolver: Any,
    cli_overrides: dict[str, Any],
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> int:
    cfg = load_renderer_config(resolver)
    cfg = _apply_overrides(cfg, cli_overrides)
    if cfg.launcher_mode == "disabled":
        return 0

    ok, root, rel_path, err = resolve_launcher_inputs(
        engine=engine,
        cfg=cfg,
        input_fn=input_fn,
        print_fn=print_fn,
    )
    if not ok:
        print_fn(err or "ERROR: unable to resolve launcher inputs")
        return 1

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
        nav_ui=cfg.nav_ui,
    )


def _pick_root(*_args: Any, **_kwargs: Any) -> str:  # pragma: no cover
    raise RuntimeError("_pick_root moved to cli_launcher_facade")


def _pick_path(*_args: Any, **_kwargs: Any) -> str:  # pragma: no cover
    raise RuntimeError("_pick_path moved to cli_launcher_facade")


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

        if int(state.get("phase") or 1) == 2:
            return _finalize(engine, session_id, print_fn=print_fn)

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
            if int(state2.get("phase") or 1) == 2:
                return _finalize(engine, session_id, print_fn=print_fn)
            continue

        if cfg.noninteractive:
            print_fn("ERROR: noninteractive mode requires explicit wizard step payloads.")
            return 1

        nav_ui = str(getattr(cfg, "nav_ui", "prompt"))
        allow_inline = nav_ui in {"inline", "both"}
        show_action_prompt = nav_ui in {"prompt", "both"}

        def _handle_inline_nav(
            raw: str, *, _allow_inline: bool = allow_inline
        ) -> tuple[bool, int | None]:
            if not _allow_inline:
                return False, None
            expr = str(raw or "").strip().lower()
            if expr in {":back", "back"}:
                engine.apply_action(session_id, "back")
                return True, None
            if expr in {":cancel", "cancel"}:
                engine.apply_action(session_id, "cancel")
                return True, 1
            return False, None

        payload: dict[str, Any] = {}
        back_requested = False

        for f in fields:
            name = f.get("name")
            ftype = f.get("type")
            if not isinstance(name, str) or not isinstance(ftype, str):
                continue

            if ftype == "multi_select_indexed":
                _show_select_items(field=f, name=name, cfg=cfg, print_fn=print_fn)
                expr = input_fn(f"{name} selection (e.g. all, 1,3,5-8): ").strip()
                handled, rc = _handle_inline_nav(expr)
                if handled:
                    if rc is not None:
                        return rc
                    back_requested = True
                    break
                payload[f"{name}_expr"] = expr
                continue

            if ftype in {"toggle", "confirm"}:
                raw = input_fn(f"{name} (y/n): ").strip().lower()
                handled, rc = _handle_inline_nav(raw)
                if handled:
                    if rc is not None:
                        return rc
                    back_requested = True
                    break
                payload[name] = raw in {"y", "yes", "1", "true", "t"}
                continue

            if ftype == "number":
                raw = input_fn(f"{name} (int): ").strip()
                handled, rc = _handle_inline_nav(raw)
                if handled:
                    if rc is not None:
                        return rc
                    back_requested = True
                    break
                try:
                    payload[name] = int(raw)
                except Exception:
                    payload[name] = raw
                continue

            if ftype in {"text", "select"}:
                raw = input_fn(f"{name}: ").rstrip("\n")
                handled, rc = _handle_inline_nav(raw)
                if handled:
                    if rc is not None:
                        return rc
                    back_requested = True
                    break
                payload[name] = raw
                continue

            # Fallback: ask for raw JSON value.
            raw = input_fn(f"{name} (raw): ").rstrip("\n")
            handled, rc = _handle_inline_nav(raw)
            if handled:
                if rc is not None:
                    return rc
                back_requested = True
                break
            payload[name] = raw

        if back_requested:
            continue

        state3 = engine.submit_step(session_id, cur, payload)
        if int(state3.get("phase") or 1) == 2:
            return _finalize(engine, session_id, print_fn=print_fn)

        if show_action_prompt:
            nav = input_fn("Action (:next, :back, :cancel, Enter=continue): ").strip().lower()
            if nav in {":next", "next"}:
                engine.apply_action(session_id, "next")
            elif nav in {":back", "back"}:
                engine.apply_action(session_id, "back")
            elif nav in {":cancel", "cancel"}:
                engine.apply_action(session_id, "cancel")
                return 1

        continue


def _show_select_items(
    *,
    field: dict[str, Any],
    name: str,
    cfg: RendererConfig,
    print_fn: Callable[[str], None],
) -> None:
    items_any = field.get("items")
    if not (isinstance(items_any, list) and all(isinstance(x, dict) for x in items_any)):
        print_fn(f"ERROR: field '{name}' has no selectable items")
        return

    items: list[dict[str, Any]] = [dict(x) for x in items_any]
    if not items:
        print_fn(f"ERROR: field '{name}' has no selectable items")
        return

    print_fn(f"Selectable items for '{name}':")
    for idx, it in enumerate(items[: cfg.max_list_items], start=1):
        label = str(it.get("display_label") or it.get("label") or "")
        item_id = str(it.get("item_id") or "")
        if cfg.show_internal_ids and item_id:
            print_fn(f"  {idx}. {label} [{item_id}]")
        else:
            print_fn(f"  {idx}. {label}")
    if len(items) > cfg.max_list_items:
        print_fn(f"  ... ({len(items) - cfg.max_list_items} more)")


def _finalize(
    engine: ImportWizardEngine, session_id: str, *, print_fn: Callable[[str], None]
) -> int:
    return begin_phase2(engine, session_id, print_fn=print_fn)
