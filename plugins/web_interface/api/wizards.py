from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..util.fs import find_repo_root
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

    out = {"wizard": {**wiz, "steps": norm_steps}}

    # Prefer project dumper if available
    try:
        from ..util.yamlutil import safe_dump_yaml
    except Exception:
        safe_dump_yaml = None

    if safe_dump_yaml is not None:
        dumped = safe_dump_yaml(out)
        if dumped is not None:
            return dumped

    import yaml

    return yaml.safe_dump(out, sort_keys=False, allow_unicode=True)


class WizardPut(BaseModel):
    yaml: str | None = None
    model: dict[str, Any] | None = None


class WizardCreate(BaseModel):
    name: str
    yaml: str


def _wizards_dir() -> Path:
    repo = find_repo_root()
    d = repo / "wizards"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _wizard_path(name: str) -> Path:
    d = _wizards_dir()
    if not name.endswith(".yaml") and not name.endswith(".yml"):
        name = name + ".yaml"
    return d / name


def _parse_steps_fallback(text: str) -> list[dict[str, Any]]:
    # heuristic: find "steps:" then parse subsequent list items with "name/title/type"
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
            if cur:
                steps.append(cur)
            cur = {}
            rest = m.group(1).strip()
            if rest and ":" in rest:
                k, v = rest.split(":", 1)
                cur[k.strip()] = v.strip().strip("'\"")
        else:
            m2 = re.match(r"^\s+([A-Za-z0-9_\-]+)\s*:\s*(.*)$", ln)
            if m2 and cur is not None:
                cur[m2.group(1)] = m2.group(2).strip().strip("'\"")
        i += 1
    if cur:
        steps.append(cur)
    return steps


def mount_wizards(app: FastAPI) -> None:
    @app.get("/api/wizards")
    def list_wizards() -> dict[str, Any]:
        d = _wizards_dir()
        items = []
        for p in sorted(d.glob("*.y*ml")):
            items.append({"name": p.stem})
        return {"items": items}

    @app.get("/api/wizards/{name}")
    def get_wizard(name: str) -> dict[str, Any]:
        p = _wizard_path(name)
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        return {"name": p.stem, "yaml": p.read_text(encoding="utf-8")}

    @app.get("/api/wizards/{name}/parsed")
    def get_wizard_parsed(name: str) -> dict[str, Any]:
        p = _wizard_path(name)
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        text = p.read_text(encoding="utf-8")
        obj = safe_load_yaml(text)
        wizard: dict[str, Any] = {}
        steps: list[dict[str, Any]] = []
        if isinstance(obj, dict):
            wizard = obj
            st = obj.get("steps")
            if isinstance(st, list):
                steps = [s if isinstance(s, dict) else {"value": s} for s in st]
        if not steps:
            steps = _parse_steps_fallback(text)
        return {"name": p.stem, "yaml": text, "wizard": wizard, "steps": steps}

    @app.post("/api/wizards")
    def create_wizard(body: WizardCreate) -> dict[str, Any]:
        p = _wizard_path(body.name)
        if p.exists():
            raise HTTPException(status_code=409, detail="exists")
        p.write_text(body.yaml, encoding="utf-8")
        return {"ok": True, "name": p.stem}

    @app.put("/api/wizards/{name}")
    def put_wizard(name: str, body: WizardPut) -> dict[str, Any]:
        p = _wizard_path(name)
        if body.yaml is None:
            raise HTTPException(status_code=400, detail="missing 'yaml'")
        p.write_text(body.yaml, encoding="utf-8")
        return {"ok": True, "name": p.stem}

    @app.delete("/api/wizards/{name}")
    def delete_wizard(name: str) -> dict[str, Any]:
        p = _wizard_path(name)
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        p.unlink()
        return {"ok": True}

    @app.post("/api/wizards/preview")
    def preview_wizard(body: dict[str, Any]) -> dict[str, Any]:
        model = body.get("model")
        if model is None or not isinstance(model, dict):
            raise HTTPException(status_code=400, detail="missing 'model'")
        try:
            yaml_text = _serialize_wizard_model(model)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"yaml": yaml_text}
