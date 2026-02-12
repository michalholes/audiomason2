from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from audiomason.core.wizard_service import WizardService

from ..util.paths import debug_enabled
from ..util.yamlutil import safe_load_yaml


def _parse_wizard_model(yaml_text: str) -> dict[str, Any]:
    data = safe_load_yaml(yaml_text)
    if not isinstance(data, dict) or "wizard" not in data:
        raise ValueError("invalid wizard yaml: missing top-level 'wizard'")
    wiz = data.get("wizard")
    if not isinstance(wiz, dict):
        raise ValueError("invalid wizard yaml: 'wizard' must be a mapping")
    steps = wiz.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("invalid wizard yaml: 'wizard.steps' must be a list")

    model_steps: list[dict[str, Any]] = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            model_steps.append({"id": f"step_{i + 1}", "type": "unknown", "raw": s})
            continue
        sid = s.get("id") or f"step_{i + 1}"
        stype = s.get("type") or "unknown"
        step = {"id": sid, "type": stype, **s}
        model_steps.append(step)

    return {"wizard": {**wiz, "steps": model_steps}}


def _serialize_wizard_model(model: dict[str, Any]) -> str:
    if not isinstance(model, dict) or "wizard" not in model:
        raise ValueError("invalid model: missing 'wizard'")
    wiz = model.get("wizard")
    if not isinstance(wiz, dict):
        raise ValueError("invalid model: 'wizard' must be a mapping")

    steps = wiz.get("steps") or []
    if not isinstance(steps, list):
        raise ValueError("invalid model: 'wizard.steps' must be a list")

    # Preserve a small, explicitly allowed UI metadata namespace under wizard._ui.
    ui_allowed = {"defaults_memory", "templates"}
    ui_raw = wiz.get("_ui")
    ui: dict[str, Any] | None = None
    if isinstance(ui_raw, dict):
        ui = {k: v for k, v in ui_raw.items() if k in ui_allowed}

    norm_steps: list[dict[str, Any]] = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            norm_steps.append({"id": f"step_{i + 1}", "type": "unknown", "raw": s})
            continue
        sid = s.get("id") or f"step_{i + 1}"
        stype = s.get("type") or "unknown"
        cleaned = {k: v for k, v in s.items() if k not in {"_ui"}}
        cleaned["id"] = sid
        cleaned["type"] = stype
        norm_steps.append(cleaned)

    out_wiz = {**wiz, "steps": norm_steps}
    if ui is not None:
        out_wiz["_ui"] = ui
    else:
        out_wiz.pop("_ui", None)

    out = {"wizard": out_wiz}

    # Prefer project dumper if available
    try:
        from ..util.yamlutil import safe_dump_yaml
    except Exception:
        safe_dump_yaml_fn = None
    else:
        safe_dump_yaml_fn = safe_dump_yaml

    if safe_dump_yaml_fn is not None:
        dumped = safe_dump_yaml_fn(out)
        if dumped is not None:
            return dumped

    import yaml

    return yaml.safe_dump(out, sort_keys=False, allow_unicode=False)


def _validate_wizard_model(model: dict[str, Any]) -> None:
    """Strict server-side validation for safe saving.

    The goal is to prevent saving obviously invalid or non-deterministic wizard
    definitions from the visual editor, while still accepting legacy files on
    read-only paths.
    """

    if not isinstance(model, dict) or "wizard" not in model:
        raise ValueError("invalid model: missing 'wizard'")
    wiz = model.get("wizard")
    if not isinstance(wiz, dict):
        raise ValueError("invalid model: 'wizard' must be a mapping")

    steps = wiz.get("steps")
    if not isinstance(steps, list):
        raise ValueError("invalid model: 'wizard.steps' must be a list")

    ids: set[str] = set()
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise ValueError(f"invalid step at index {i}: step must be a mapping")
        sid = s.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError(f"invalid step at index {i}: missing 'id'")
        if sid in ids:
            raise ValueError(f"duplicate step id: {sid}")
        ids.add(sid)
        stype = s.get("type")
        if not isinstance(stype, str) or not stype.strip():
            raise ValueError(f"invalid step '{sid}': missing 'type'")

        enabled = s.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"invalid step '{sid}': 'enabled' must be boolean")

        # Keep conditions and templates as data-only structures.
        # Enforce that they are YAML/JSON-like.
        if "when" in s and not isinstance(
            s.get("when"), (dict, list, str, int, float, bool, type(None))
        ):
            raise ValueError(f"invalid step '{sid}': 'when' must be JSON/YAML-like")

        if "defaults" in s and not isinstance(s.get("defaults"), (dict, type(None))):
            raise ValueError(f"invalid step '{sid}': 'defaults' must be a mapping or null")

    ui = wiz.get("_ui")
    if ui is not None and not isinstance(ui, dict):
        raise ValueError("invalid wizard: '_ui' must be a mapping")

    # allowed keys only
    if isinstance(ui, dict):
        for k in ui:
            if k not in {"defaults_memory", "templates"}:
                raise ValueError(f"invalid wizard: unsupported _ui key '{k}'")
        if "defaults_memory" in ui and not isinstance(ui.get("defaults_memory"), dict):
            raise ValueError("invalid wizard: _ui.defaults_memory must be a mapping")
        if "templates" in ui and not isinstance(ui.get("templates"), dict):
            raise ValueError("invalid wizard: _ui.templates must be a mapping")


def _validate_wizard_yaml(yaml_text: str) -> None:
    data = safe_load_yaml(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("wizard yaml must be a mapping")
    wiz = data.get("wizard")
    if not isinstance(wiz, dict):
        raise ValueError("wizard yaml: missing 'wizard' mapping")
    model = _parse_wizard_model(yaml_text)
    _validate_wizard_model(model)


class WizardPut(BaseModel):
    yaml: str | None = None
    model: dict[str, Any] | None = None


class WizardCreate(BaseModel):
    name: str
    yaml: str


def _service() -> WizardService:
    return WizardService()


def _parse_steps_fallback(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not re.match(r"^\s*steps\s*:\s*$", lines[i]):
        i += 1
    if i >= len(lines):
        return []
    i += 1
    steps: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\S", ln):
            break
        m = re.match(r"^\s*-\s*(.*)$", ln)
        if m:
            if cur is not None:
                steps.append(cur)
            cur = {"raw": m.group(1).strip()}
        elif cur is not None:
            m2 = re.match(r"^\s*(\w+)\s*:\s*(.*)$", ln)
            if m2:
                cur[m2.group(1)] = m2.group(2).strip().strip("'\"")
        i += 1
    if cur is not None:
        steps.append(cur)
    return steps


def mount_wizards(app: FastAPI) -> None:
    svc = _service()

    @app.get("/api/wizards")
    def list_wizards(request: Request) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for w in svc.list_wizards():
            item: dict[str, Any] = {"name": w.name}
            try:
                text = svc.get_wizard_text(w.name)
                parsed = safe_load_yaml(text)
                wiz = parsed.get("wizard") if isinstance(parsed, dict) else None
                if isinstance(wiz, dict):
                    if isinstance(wiz.get("name"), str) and wiz.get("name"):
                        item["display_name"] = wiz["name"]
                    if isinstance(wiz.get("description"), str) and wiz.get("description"):
                        item["description"] = wiz["description"]
                    steps = wiz.get("steps")
                    if isinstance(steps, list):
                        item["step_count"] = len(steps)
            except Exception:
                # Best-effort: listing should not fail if one wizard is malformed.
                pass
            items.append(item)
        out: dict[str, Any] = {"items": items}
        if int(getattr(request.app.state, "verbosity", 1)) >= 3 or debug_enabled():
            out["dir"] = str(svc.wizards_dir)
        return out

    @app.post("/api/wizards/preview")
    def preview_wizard(body: WizardPut) -> dict[str, Any]:
        if body.model is None:
            raise HTTPException(status_code=400, detail="expected model")
        try:
            yaml_text = _serialize_wizard_model(body.model)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"yaml": yaml_text}

    @app.post("/api/wizards/validate")
    def validate_wizard(body: WizardPut) -> dict[str, Any]:
        try:
            if body.model is not None:
                _validate_wizard_model(body.model)
                yaml_text = _serialize_wizard_model(body.model)
                return {"ok": True, "yaml": yaml_text, "model": body.model}
            if body.yaml is not None:
                _validate_wizard_yaml(body.yaml)
                model = _parse_wizard_model(body.yaml)
                return {"ok": True, "yaml": body.yaml, "model": model}
            raise HTTPException(status_code=400, detail="expected yaml or model")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @app.get("/api/wizards/{name}")
    def get_wizard(name: str) -> dict[str, Any]:
        try:
            text = svc.get_wizard_text(name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        model: dict[str, Any] | None = None
        try:
            model = _parse_wizard_model(text)
        except Exception:
            # best-effort UI model
            model = {"wizard": {"steps": _parse_steps_fallback(text)}}
        return {"name": name, "yaml": text, "model": model}

    @app.post("/api/wizards")
    def create_wizard(body: WizardCreate) -> dict[str, Any]:
        try:
            _validate_wizard_yaml(body.yaml)
            svc.put_wizard_text(body.name, body.yaml)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True}

    @app.put("/api/wizards/{name}")
    def update_wizard(name: str, body: WizardPut) -> dict[str, Any]:
        if body.yaml is None and body.model is None:
            raise HTTPException(status_code=400, detail="expected yaml or model")
        try:
            if body.yaml is not None:
                _validate_wizard_yaml(body.yaml)
                svc.put_wizard_text(name, body.yaml)
            else:
                _validate_wizard_model(body.model or {})
                yaml_text = _serialize_wizard_model(body.model or {})
                svc.put_wizard_text(name, yaml_text)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True}

    @app.delete("/api/wizards/{name}")
    def delete_wizard(name: str) -> dict[str, Any]:
        try:
            svc.delete_wizard(name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"ok": True}
