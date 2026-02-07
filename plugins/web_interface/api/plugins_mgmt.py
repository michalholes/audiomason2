from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile

from audiomason.core.config_service import ConfigService
from audiomason.core.loader import PluginLoader
from audiomason.core.plugin_registry import PluginRegistry

from ..util.fs import find_repo_root
from ..util.yamlutil import safe_load_yaml


def _read_plugin_meta(path: Path) -> dict[str, Any]:
    y = path / "plugin.yaml"
    meta: dict[str, Any] = {"name": path.name}
    if y.exists():
        obj = safe_load_yaml(y.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            meta.update({k: obj.get(k) for k in ["name", "version", "description"] if k in obj})
            if "interfaces" in obj:
                meta["interfaces"] = obj.get("interfaces")
    meta.setdefault("version", "")
    meta.setdefault("interfaces", "")
    return meta


def _user_plugins_root() -> Path:
    return Path.home() / ".audiomason/plugins"


def mount_plugins_mgmt(app: FastAPI) -> None:
    @app.get("/api/plugins")
    def list_plugins() -> dict[str, Any]:
        repo = find_repo_root()
        cfg = ConfigService()
        reg = PluginRegistry(cfg)

        loader = PluginLoader(
            builtin_plugins_dir=repo / "plugins", user_plugins_dir=_user_plugins_root()
        )
        dirs = loader.discover()

        plugin_ids: list[str] = []
        items: list[dict[str, Any]] = []
        for d in sorted(dirs):
            if not d.is_dir():
                continue
            meta = _read_plugin_meta(d)
            pid = str(meta.get("name") or d.name)
            meta["name"] = pid
            plugin_ids.append(pid)
            if str(d).startswith(str(_user_plugins_root())):
                meta["source"] = "user"
            else:
                meta["source"] = "builtin"
            items.append(meta)

        states = {s.plugin_id: s.enabled for s in reg.list_states(plugin_ids)}
        for it in items:
            pid = str(it.get("name"))
            it["enabled"] = bool(states.get(pid, True))

        return {"items": items}

    @app.post("/api/plugins/{name}/enable")
    def enable_plugin(name: str) -> dict[str, Any]:
        cfg = ConfigService()
        reg = PluginRegistry(cfg)
        reg.set_enabled(name, True)
        return {"ok": True}

    @app.post("/api/plugins/{name}/disable")
    def disable_plugin(name: str) -> dict[str, Any]:
        cfg = ConfigService()
        reg = PluginRegistry(cfg)
        reg.set_enabled(name, False)
        return {"ok": True}

    @app.delete("/api/plugins/{name}")
    def delete_plugin(name: str) -> dict[str, Any]:
        # Only allow deleting user-installed plugins.
        root = _user_plugins_root()
        target = (root / name).resolve()
        if root not in target.parents and target != root:
            raise HTTPException(status_code=400, detail="invalid path")
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="plugin not found")

        import shutil

        shutil.rmtree(target)
        return {"ok": True}

    @app.post("/api/plugins/upload")
    async def upload_plugin(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        if not file.filename or not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="expected .zip")
        data = await file.read()
        root = _user_plugins_root()
        root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = [n for n in z.namelist() if n and not n.endswith("/")]
            top = set(n.split("/")[0] for n in names)

            # Accept either plugins/<name>/... or <name>/...
            strip = "plugins/" if "plugins" in top else ""

            for n in names:
                if strip and not n.startswith(strip):
                    continue
                rel = n[len(strip) :] if strip else n
                rel = rel.lstrip("/")

                # Prevent path traversal.
                rel = rel.replace("..", "_")
                out = (root / rel).resolve()
                if root not in out.parents and out != root:
                    raise HTTPException(status_code=400, detail="invalid path")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(n))

        return {"ok": True}
