from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..util.fs import find_repo_root
from ..util.yamlutil import safe_load_yaml


class WizardPut(BaseModel):
    yaml: str


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
        p.write_text(body.yaml, encoding="utf-8")
        return {"ok": True, "name": p.stem}

    @app.delete("/api/wizards/{name}")
    def delete_wizard(name: str) -> dict[str, Any]:
        p = _wizard_path(name)
        if not p.exists():
            raise HTTPException(status_code=404, detail="not found")
        p.unlink()
        return {"ok": True}
