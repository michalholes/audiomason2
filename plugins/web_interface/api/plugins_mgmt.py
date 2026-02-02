from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile

from ..util.fs import find_repo_root
from ..util.paths import plugins_root
from ..util.yamlutil import safe_load_yaml
from ._am_cfg import (
    get_disabled_plugins,
    read_am_config_text,
    set_disabled_plugins,
    write_am_config_text,
)


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


def mount_plugins_mgmt(app: FastAPI) -> None:
    @app.get("/api/plugins")
    def list_plugins() -> dict[str, Any]:
        repo = find_repo_root()
        root = plugins_root(repo)
        disabled = set(get_disabled_plugins(read_am_config_text()))
        items: list[dict[str, Any]] = []
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            meta = _read_plugin_meta(p)
            name = str(meta.get("name") or p.name)
            meta["name"] = name
            meta["enabled"] = name not in disabled
            items.append(meta)
        return {"items": items}

    @app.post("/api/plugins/{name}/enable")
    def enable_plugin(name: str) -> dict[str, Any]:
        txt = read_am_config_text()
        disabled = [x for x in get_disabled_plugins(txt) if x != name]
        write_am_config_text(set_disabled_plugins(txt, disabled))
        return {"ok": True}

    @app.post("/api/plugins/{name}/disable")
    def disable_plugin(name: str) -> dict[str, Any]:
        txt = read_am_config_text()
        disabled = get_disabled_plugins(txt)
        if name not in disabled:
            disabled.append(name)
        write_am_config_text(set_disabled_plugins(txt, disabled))
        return {"ok": True}

    @app.delete("/api/plugins/{name}")
    def delete_plugin(name: str) -> dict[str, Any]:
        repo = find_repo_root()
        root = plugins_root(repo)
        target = root / name
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=404, detail="plugin not found")
        # refuse to delete web_interface itself
        if name == "web_interface":
            raise HTTPException(status_code=400, detail="refuse to delete web_interface")
        import shutil

        shutil.rmtree(target)
        return {"ok": True}

    @app.post("/api/plugins/upload")
    async def upload_plugin(file: Annotated[UploadFile, File()]) -> dict[str, Any]:
        if not file.filename or not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="expected .zip")
        data = await file.read()
        repo = find_repo_root()
        root = plugins_root(repo)
        root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            # require zip to contain plugins/<name>/...
            names = [n for n in z.namelist() if n and not n.endswith("/")]
            top = set(n.split("/")[0] for n in names)
            if "plugins" in top:
                # strip optional leading folder
                for n in names:
                    if not n.startswith("plugins/"):
                        continue
                    rel = n[len("plugins/") :]
                    if not rel:
                        continue
                    out = root / rel
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(z.read(n))
            else:
                raise HTTPException(status_code=400, detail="zip must contain plugins/<name>/...")
        return {"ok": True}
