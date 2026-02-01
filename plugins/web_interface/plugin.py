from __future__ import annotations

import io
import os
import re
import time
import json

try:
    import yaml as _yaml  # type: ignore
except Exception:  # pragma: no cover
    _yaml = None
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


@dataclass(frozen=True)
class NavItem:
    title: str
    route: str
    page_id: str



def _extract_steps_from_yaml(yaml_text: str) -> list[dict[str, str]]:
    """Best-effort extraction of wizard steps from AM wizard YAML without requiring a YAML parser.

    Expects format:
      wizard:
        steps:
          - id: ...
            type: ...
            prompt: ...
    Returns list of dicts with keys: id, type, prompt.
    """
    steps: list[dict[str, str]] = []
    in_steps = False
    cur: dict[str, str] | None = None

    def flush() -> None:
        nonlocal cur
        if cur and cur.get("id"):
            steps.append(cur)
        cur = None

    for raw in yaml_text.splitlines():
        line = raw.rstrip("\n")
        # detect steps section (allow comments/blank)
        if not in_steps:
            if re.match(r"^\s*steps\s*:\s*$", line):
                in_steps = True
            continue

        # stop if indentation drops back to <= 2 spaces (new top-level key)
        if re.match(r"^\S", line):
            break

        m_item = re.match(r"^\s*-\s+id\s*:\s*(.+)\s*$", line)
        if m_item:
            flush()
            cur = {"id": m_item.group(1).strip().strip('"').strip("'")}
            continue

        if cur is None:
            continue

        m_type = re.match(r"^\s*type\s*:\s*(.+)\s*$", line)
        if m_type and "type" not in cur:
            cur["type"] = m_type.group(1).strip().strip('"').strip("'")
            continue

        m_prompt = re.match(r"^\s*prompt\s*:\s*(.+)\s*$", line)
        if m_prompt and "prompt" not in cur:
            cur["prompt"] = m_prompt.group(1).strip().strip('"').strip("'")
            continue

    flush()
    return steps
class WebInterfacePlugin:
    """
    Standalone web UI plugin (no dependency on web_server plugin).

    Provides:
      - /ui/ (static renderer: app.js + app.css)
      - SPA routes: /, /plugins, /stage, /wizards, /logs, /ui-config
      - API: /api/ui/*, /api/plugins*, /api/stage*, /api/wizards*, /api/logs*
    """

    def __init__(self) -> None:
        here = Path(__file__).resolve().parent
        self._repo_root = here.parent.parent.resolve()
        self._ui_dir = here / "ui"

    # ----------------------------
    # Config / paths
    # ----------------------------

    def _config_dir(self) -> Path:
        return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "audiomason"

    def _read_main_config(self) -> dict[str, Any]:
        # ~/.config/audiomason/config.yaml (very small subset needed here)
        cfg_path = self._config_dir() / "config.yaml"
        if not cfg_path.exists():
            return {}
        # Try PyYAML if installed, else minimal key:value parser
        try:
            import yaml  # type: ignore
        except Exception:
            out: dict[str, Any] = {}
            for line in cfg_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip()
            return out
        else:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))  # type: ignore
            return data if isinstance(data, dict) else {}

    def _stage_dir(self) -> Path:
        cfg = self._read_main_config()
        inbox = cfg.get("inbox_dir") if isinstance(cfg, dict) else None
        if isinstance(inbox, str) and inbox:
            return Path(inbox) / "stage"
        env = os.environ.get("WEB_INTERFACE_STAGE_DIR")
        if env:
            return Path(env)
        return self._repo_root / "stage"

    def _wizards_dir(self) -> Path:
        # Keep consistent with earlier behavior: repo_root/wizards
        return self._repo_root / "wizards"

    def _plugins_root(self) -> Path:
        return self._repo_root / "plugins"

    def _ui_config_path(self) -> Path:
        return Path(os.environ.get("WEB_INTERFACE_UI_CONFIG", str(self._config_dir() / "web_interface_ui.json")))

    def _effective_ui_snapshot(self) -> dict[str, Any]:
        pages = self._default_pages()
        nav_items: list[dict[str, Any]] = []
        for ni in self._default_nav():
            nav_items.append({"title": ni.title, "route": ni.route, "page_id": ni.page_id})
        return {"pages": pages, "nav": nav_items}

    def _log_path(self) -> Optional[Path]:
        p = os.environ.get("WEB_INTERFACE_LOG_PATH")
        if not p:
            return None
        return Path(p)

    # ----------------------------
    # AM config + plugins enable/disable (parity with old web_server)
    # ----------------------------

    def _am_config_path(self) -> Path:
        return self._config_dir() / "config.yaml"

    def _load_am_config(self) -> dict[str, Any]:
        p = self._am_config_path()
        if not p.exists():
            return {}
        try:
            import yaml  # type: ignore
        except Exception:
            # If PyYAML is missing, treat config as empty rather than guessing.
            return {}
        try:
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_am_config(self, data: dict[str, Any]) -> None:
        p = self._am_config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise RuntimeError("PyYAML required to write config.yaml") from e
        with p.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _get_disabled_plugins(self) -> list[str]:
        cfg = self._load_am_config()
        plugins = cfg.get("plugins")
        if not isinstance(plugins, dict):
            return []
        disabled = plugins.get("disabled")
        if not isinstance(disabled, list):
            return []
        return [x for x in disabled if isinstance(x, str) and x.strip()]

    def _set_plugin_enabled(self, name: str, enabled: bool, *, remove: bool = False) -> None:
        cfg = self._load_am_config()
        if not isinstance(cfg.get("plugins"), dict):
            cfg["plugins"] = {}
        plugins = cfg["plugins"]
        if not isinstance(plugins, dict):
            plugins = {}
            cfg["plugins"] = plugins
        disabled = plugins.get("disabled")
        if not isinstance(disabled, list):
            disabled = []
            plugins["disabled"] = disabled

        # normalize
        disabled = [x for x in disabled if isinstance(x, str)]
        if remove:
            disabled = [x for x in disabled if x != name]
        else:
            if enabled:
                disabled = [x for x in disabled if x != name]
            else:
                if name not in disabled:
                    disabled.append(name)

        plugins["disabled"] = disabled
        self._save_am_config(cfg)

    def _is_enabled(self, name: str) -> bool:
        return name not in set(self._get_disabled_plugins())

    # ----------------------------
    # UI schema
    # ----------------------------
    # ----------------------------
    # UI schema
    # ----------------------------

    def _default_pages(self) -> dict[str, dict[str, Any]]:
        return {
            "dashboard": {
                "id": "dashboard",
                "title": "Dashboard",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "Status",
                            "content": {
                                "type": "stat_list",
                                "source": {"type": "api", "path": "/api/status"},
                                "fields": [
                                    {"label": "Version", "key": "version"},
                                    {"label": "Uptime", "key": "uptime"},
                                    {"label": "PID", "key": "pid"},
                                ],
                            },
                        }
                    ],
                },
            },
            "config": {
                "id": "config",
                "title": "Config",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "AudioMason config.yaml",
                            "content": {
                                "type": "yaml_editor",
                                "source": {"type": "api", "path": "/api/am/config"},
                                "save_action": {"type": "api", "method": "PUT", "path": "/api/am/config"},
                            },
                        }
                    ],
                },
            },
            "plugins": {
                "id": "plugins",
                "title": "Plugins",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "Plugins",
                            "content": {"type": "plugin_manager", "source": {"type": "api", "path": "/api/plugins"}},
                        }
                    ],
                },
            },
            "stage": {
                "id": "stage",
                "title": "Stage",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "Stage",
                            "content": {"type": "stage_manager"},
                        }
                    ],
                },
            },
            "wizards": {
                "id": "wizards",
                "title": "Wizards",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "Wizards",
                            "content": {"type": "wizard_manager"},
                        }
                    ],
                },
            },
            "logs": {
                "id": "logs",
                "title": "Logs",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "Live logs",
                            "content": {
                                "type": "log_stream",
                                "tail_source": {"type": "api", "path": "/api/logs/tail?lines=200"},
                                "source": {"type": "sse", "path": "/api/logs/stream"},
                            },
                        }
                    ],
                },
            },
            "ui_config": {
                "id": "ui_config",
                "title": "UI Config",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "UI overrides (WEB_INTERFACE_UI_CONFIG)",
                            "content": {
                                "type": "json_editor",
                                "source": {"type": "api", "path": "/api/ui/config"},
                                "save_action": {"type": "api", "method": "PUT", "path": "/api/ui/config"},
                            },
                        }
                    ],
                },
            },
        }

    def _default_nav(self) -> list[NavItem]:
        return [
            NavItem("Dashboard", "/", "dashboard"),
            NavItem("Config", "/config", "config"),
            NavItem("Plugins", "/plugins", "plugins"),
            NavItem("Stage", "/stage", "stage"),
            NavItem("Wizards", "/wizards", "wizards"),
            NavItem("Logs", "/logs", "logs"),
            NavItem("UI Config", "/ui-config", "ui_config"),
        ]

    def _load_ui_overrides(self) -> dict[str, Any]:
        p = self._ui_config_path()
        if not p.exists():
            return {"pages": {}, "nav": []}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"pages": {}, "nav": []}
        return data if isinstance(data, dict) else {"pages": {}, "nav": []}

    def _save_ui_overrides(self, data: dict[str, Any]) -> None:
        p = self._ui_config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _effective_pages_and_nav(self) -> tuple[dict[str, dict[str, Any]], list[NavItem]]:
        pages = self._default_pages()
        nav = self._default_nav()

        ov = self._load_ui_overrides()
        ov_pages = ov.get("pages")
        if isinstance(ov_pages, dict):
            for k, v in ov_pages.items():
                if isinstance(k, str) and isinstance(v, dict):
                    vv = dict(v)
                    vv.setdefault("id", k)
                    pages[k] = vv

        ov_nav = ov.get("nav")
        if isinstance(ov_nav, list):
            out: list[NavItem] = []
            for it in ov_nav:
                if not isinstance(it, dict):
                    continue
                t = it.get("title")
                r = it.get("route")
                pid = it.get("page_id")
                if isinstance(t, str) and isinstance(r, str) and isinstance(pid, str):
                    out.append(NavItem(t, r, pid))
            if out:
                nav = out

        return pages, nav

    # ----------------------------
    # API util: plugins metadata
    # ----------------------------

    def _iter_plugins(self) -> Iterable[tuple[str, Path]]:
        root = self._plugins_root()
        if not root.exists():
            return []
        out: list[tuple[str, Path]] = []
        for p in sorted(root.iterdir()):
            if p.is_dir():
                out.append((p.name, p))
        return out

    def _read_plugin_yaml(self, path: Path) -> dict[str, Any]:
        y = path / "plugin.yaml"
        if not y.exists():
            return {}
        try:
            import yaml  # type: ignore
        except Exception:
            return {}
        data = yaml.safe_load(y.read_text(encoding="utf-8"))  # type: ignore
        return data if isinstance(data, dict) else {}

    # ----------------------------
    # Logs
    # ----------------------------

    def _tail_text(self, path: Path, lines: int) -> str:
        # tail without reading full file; simple block read from end
        n = max(1, min(int(lines), 5000))
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b""
            pos = size
            while pos > 0 and data.count(b"\n") <= n:
                read = block if pos - block > 0 else pos
                pos -= read
                f.seek(pos, os.SEEK_SET)
                data = f.read(read) + data
            txt = data.decode("utf-8", errors="replace")
        parts = txt.splitlines()
        return "\n".join(parts[-n:])

    def _sse_follow(self, path: Path):
        # simple poll-follow
        last_size = 0
        while True:
            try:
                cur = path.stat().st_size
            except Exception:
                cur = 0
            if cur < last_size:
                last_size = 0  # rotated/truncated
            if cur > last_size:
                with path.open("rb") as f:
                    f.seek(last_size)
                    chunk = f.read(cur - last_size)
                    last_size = cur
                text = chunk.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    yield f"data: {line}\n\n"
            time.sleep(0.5)

    # ----------------------------
    # App factory
    # ----------------------------

    def _index_html(self) -> str:
        idx = self._ui_dir / "index.html"
        if not idx.exists():
            return "<html><body><h1>web_interface UI missing</h1></body></html>"
        return idx.read_text(encoding="utf-8")

    def create_app(self) -> FastAPI:
        app = FastAPI(title="AudioMason web_interface")

        # UI assets
        if (self._ui_dir / "assets").exists():
            app.mount("/ui/assets", StaticFiles(directory=str(self._ui_dir / "assets")), name="ui_assets")
        else:
            raise RuntimeError(f"web_interface UI assets not found at: {self._ui_dir / 'assets'}")

        @app.get("/ui/", response_class=HTMLResponse)
        def ui_index() -> HTMLResponse:
            return HTMLResponse(self._index_html())

        # Root index (for convenience)
        @app.get("/", response_class=HTMLResponse)
        def root_index() -> HTMLResponse:
            return HTMLResponse(self._index_html())

        
        # SPA fallback for direct navigation to UI routes (e.g. /plugins, /stage, /wizards, /config)
        @app.get("/{full_path:path}", response_class=HTMLResponse)
        def spa_fallback(full_path: str) -> HTMLResponse:
            # Let API and static assets be handled by their own routes.
            if full_path.startswith("api/") or full_path.startswith("ui/assets/"):
                raise HTTPException(status_code=404, detail="Not found")
            # Normalize: serve the same SPA shell for any other GET.
            return HTMLResponse(self._index_html())

        @app.get("/api/health")
        def health() -> dict[str, Any]:
            return {"ok": True}

        @app.get("/api/status")
        def status() -> dict[str, Any]:
            return {
                "version": "web_interface",
                "uptime": int(time.time()),
                "pid": os.getpid(),
            }

        
        # AM config (edit ~/.config/audiomason/config.yaml)
        @app.get("/api/am/config")
        def am_config_get() -> dict[str, Any]:
            p = self._am_config_path()
            txt = ""
            if p.exists():
                txt = p.read_text(encoding="utf-8", errors="replace")
            return {"path": str(p), "yaml": txt}

        @app.put("/api/am/config")
        def am_config_put(payload: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(payload, dict) or not isinstance(payload.get("yaml"), str):
                raise HTTPException(status_code=400, detail="expected {'yaml': string}")
            p = self._am_config_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload["yaml"], encoding="utf-8")
            return {"ok": True, "path": str(p)}

# UI schema
        @app.get("/api/ui/nav")
        def ui_nav() -> dict[str, Any]:
            _, nav = self._effective_pages_and_nav()
            return {"items": [{"title": n.title, "route": n.route, "page_id": n.page_id} for n in nav]}

        @app.get("/api/ui/pages")
        def ui_pages() -> dict[str, Any]:
            pages, _ = self._effective_pages_and_nav()
            items = [{"id": p.get("id", k), "title": p.get("title", k)} for k, p in pages.items()]
            return {"items": items}

        @app.get("/api/ui/page/{page_id}")
        def ui_page(page_id: str) -> dict[str, Any]:
            pages, _ = self._effective_pages_and_nav()
            if page_id not in pages:
                raise HTTPException(status_code=404, detail="page not found")
            return pages[page_id]

        @app.get("/api/ui/config")
        def ui_config_get() -> dict[str, Any]:
            p = self._ui_config_path()
            data = self._load_ui_overrides()
            if (not p.exists()) and (not data):
                data = self._effective_ui_snapshot()
            return {"data": data, "info": str(p)}

        @app.put("/api/ui/config")
        def ui_config_put(payload: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(payload, dict) or "data" not in payload:
                raise HTTPException(status_code=400, detail="expected {'data': {...}}")
            data = payload["data"]
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="'data' must be object")
            self._save_ui_overrides(data)
            return {"ok": True}

        # Plugins management
        @app.get("/api/plugins")
        def plugins_list() -> dict[str, Any]:
            items: list[dict[str, Any]] = []
            for name, p in self._iter_plugins():
                meta = self._read_plugin_yaml(p)
                items.append(
                    {
                        "name": name,
                        "version": meta.get("version", ""),
                        "interfaces": meta.get("interfaces", []) if isinstance(meta.get("interfaces"), list) else [],
                        "enabled": self._is_enabled(name),
                    }
                )
            return {"items": items}

        @app.post("/api/plugins/{name}/enable")
        def plugins_enable(name: str) -> dict[str, Any]:
            self._set_plugin_enabled(name, True)
            return {"ok": True}

        @app.post("/api/plugins/{name}/disable")
        def plugins_disable(name: str) -> dict[str, Any]:
            self._set_plugin_enabled(name, False)
            return {"ok": True}

        @app.delete("/api/plugins/{name}")
        def plugins_delete(name: str) -> dict[str, Any]:
            pdir = self._plugins_root() / name
            if not pdir.exists() or not pdir.is_dir():
                raise HTTPException(status_code=404, detail="plugin not found")
            if not (pdir / "plugin.yaml").exists():
                raise HTTPException(status_code=400, detail="not a plugin dir")
            import shutil as _shutil
            _shutil.rmtree(pdir)
            self._set_plugin_enabled(name, False, remove=True)
            return {"ok": True}

        @app.post("/api/plugins/upload")
        async def plugins_upload(file: UploadFile = File(...)) -> dict[str, Any]:
            if not file.filename or not file.filename.lower().endswith(".zip"):
                raise HTTPException(status_code=400, detail="expected .zip")
            data = await file.read()
            import zipfile
            zf = zipfile.ZipFile(io.BytesIO(data))
            root = self._plugins_root()
            root.mkdir(parents=True, exist_ok=True)
            # Expect zip contains plugins/<name>/... or <name>/...
            names = [n for n in zf.namelist() if n and not n.endswith("/")]
            top = names[0].split("/")[0] if names else ""
            # Extract into a temp dir then move
            tmp = root / ".upload_tmp"
            import shutil as _shutil
            _shutil.rmtree(tmp, ignore_errors=True)
            tmp.mkdir(parents=True, exist_ok=True)
            zf.extractall(tmp)
            # locate plugin dir
            cand = None
            if (tmp / "plugins").exists():
                # choose first subdir under plugins
                subs = [p for p in (tmp / "plugins").iterdir() if p.is_dir()]
                if subs:
                    cand = subs[0]
            elif top and (tmp / top).is_dir():
                cand = tmp / top
            if cand is None:
                raise HTTPException(status_code=400, detail="zip does not contain plugin dir")
            if not (cand / "plugin.yaml").exists():
                raise HTTPException(status_code=400, detail="plugin.yaml missing in upload")
            dest = root / cand.name
            _shutil.rmtree(dest, ignore_errors=True)
            _shutil.move(str(cand), str(dest))
            _shutil.rmtree(tmp, ignore_errors=True)
            return {"ok": True, "name": dest.name}

        # Stage
        @app.get("/api/stage")
        def stage_list() -> dict[str, Any]:
            d = self._stage_dir()
            d.mkdir(parents=True, exist_ok=True)
            items: list[dict[str, Any]] = []
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    st = p.stat()
                    rel = p.relative_to(d).as_posix()
                    items.append({"name": rel, "size": st.st_size, "mtime_ts": int(st.st_mtime)})
            return {"dir": str(d), "items": items}

        @app.post("/api/stage/upload")
        async def stage_upload(
            files: list[UploadFile] = File(...),
            relpaths: list[str] = Form([]),
        ) -> dict[str, Any]:
            d = self._stage_dir()
            d.mkdir(parents=True, exist_ok=True)

            def _safe_relpath(raw: str) -> Path:
                rp = (raw or "").replace("\\", "/").lstrip("/")
                p = Path(rp)
                if p.is_absolute() or ".." in p.parts:
                    raise HTTPException(status_code=400, detail="invalid path")
                return p

            if not files:
                raise HTTPException(status_code=400, detail="missing files")

            count = 0
            for i, f in enumerate(files):
                if not f.filename:
                    continue
                raw = relpaths[i] if i < len(relpaths) and relpaths[i] else f.filename
                rel = _safe_relpath(raw)
                dest = d / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                content = await f.read()
                dest.write_bytes(content)
                count += 1

            return {"ok": True, "count": count}

        @app.delete("/api/stage/{name:path}")
        def stage_delete(name: str) -> dict[str, Any]:
            d = self._stage_dir()
            rp = (name or "").replace("\\", "/").lstrip("/")
            p = Path(rp)
            if p.is_absolute() or ".." in p.parts:
                raise HTTPException(status_code=400, detail="invalid path")
            target = d / p
            if not target.exists() or not target.is_file():
                raise HTTPException(status_code=404, detail="file not found")
            target.unlink()
            parent = target.parent
            while parent != d and parent.exists():
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
            return {"ok": True}

        # Wizards
        @app.get("/api/wizards")
        def wizards_list() -> dict[str, Any]:
            d = self._wizards_dir()
            d.mkdir(parents=True, exist_ok=True)
            items: list[dict[str, Any]] = []
            for p in sorted(d.glob("*.yaml")):
                # best-effort steps count
                steps = 0
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip().startswith("-"):
                        steps += 1
                items.append({"filename": p.stem, "steps": steps})
            return {"dir": str(d), "items": items}

        @app.get("/api/wizards/{name}")
        def wizards_get(name: str) -> dict[str, Any]:
            p = self._wizards_dir() / f"{name}.yaml"
            if not p.exists():
                raise HTTPException(status_code=404, detail="wizard not found")
            return {"yaml": p.read_text(encoding="utf-8")}

        @app.get("/api/wizards/{name}/parsed")
        def wizards_get_parsed(name: str) -> dict[str, Any]:
            p = self._wizards_dir() / f"{name}.yaml"
            if not p.exists():
                raise HTTPException(status_code=404, detail="wizard not found")
            raw = p.read_text(encoding="utf-8", errors="replace")

            parsed: Any = {}
            if _yaml is not None:
                try:
                    parsed = _yaml.safe_load(raw) or {}
                except Exception:
                    parsed = {}

            # Prefer real YAML parse, but fall back to regex extraction to ensure steps are visible
            steps: Any = []
            try:
                if isinstance(parsed, dict):
                    w = parsed.get("wizard")
                    if isinstance(w, dict):
                        s = w.get("steps")
                        if isinstance(s, list):
                            steps = s
            except Exception:
                steps = []

            if not steps:
                steps = _extract_steps_from_yaml(raw)

            wizard_out: Any = {}
            if isinstance(parsed, dict) and isinstance(parsed.get("wizard"), dict):
                wizard_out = parsed.get("wizard")
            return {"yaml": raw, "wizard": wizard_out, "steps": steps}
        @app.post("/api/wizards")
        def wizards_create(payload: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail="expected object")
            nm = payload.get("name")
            y = payload.get("yaml")
            if not isinstance(nm, str) or not nm.strip():
                raise HTTPException(status_code=400, detail="expected 'name' string")
            if not isinstance(y, str):
                raise HTTPException(status_code=400, detail="expected 'yaml' string")
            safe = "".join(ch for ch in nm.strip() if ch.isalnum() or ch in ("-","_")).strip("-_")
            if not safe:
                raise HTTPException(status_code=400, detail="invalid name")
            p = self._wizards_dir() / f"{safe}.yaml"
            if p.exists():
                raise HTTPException(status_code=409, detail="wizard exists")
            p.write_text(y, encoding="utf-8")
            return {"ok": True, "name": safe}

        @app.put("/api/wizards/{name}")
        def wizards_put(name: str, payload: dict[str, Any]) -> dict[str, Any]:
            if not isinstance(payload, dict) or not isinstance(payload.get("yaml"), str):
                raise HTTPException(status_code=400, detail="expected {'yaml': string}")
            p = self._wizards_dir() / f"{name}.yaml"
            p.write_text(payload["yaml"], encoding="utf-8")
            return {"ok": True}

        @app.delete("/api/wizards/{name}")
        def wizards_delete(name: str) -> dict[str, Any]:
            p = self._wizards_dir() / f"{name}.yaml"
            if not p.exists():
                raise HTTPException(status_code=404, detail="wizard not found")
            p.unlink()
            return {"ok": True}

        # Logs (SSE)
        @app.get("/api/logs/tail")
        def logs_tail(lines: int = 200) -> dict[str, Any]:
            lp = self._log_path()
            if lp is None or not lp.exists():
                return {"text": ""}
            return {"text": self._tail_text(lp, int(lines))}

        @app.get("/api/logs/stream")
        def logs_stream():
            lp = self._log_path()
            if lp is None or not lp.exists():
                raise HTTPException(status_code=404, detail="WEB_INTERFACE_LOG_PATH not set or missing")
            return StreamingResponse(self._sse_follow(lp), media_type="text/event-stream")

        # SPA fallback for direct links (e.g. /plugins)
        @app.get("/{path:path}", response_class=HTMLResponse)
        def spa_fallback(path: str) -> HTMLResponse:
            if path.startswith("api/") or path.startswith("ui/"):
                raise HTTPException(status_code=404, detail="not found")
            return HTMLResponse(self._index_html())

        return app

    def run(self, *, host: str, port: int) -> None:
        import uvicorn
        uvicorn.run(self.create_app(), host=host, port=port)
