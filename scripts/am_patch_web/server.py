from __future__ import annotations

import cgi
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import IO, Any, cast

from .app import App


class WebHandler(BaseHTTPRequestHandler):
    server_version = "am_patch_web/1.0.0"

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._do_get()
        except Exception as e:
            self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._do_post()
        except Exception as e:
            self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"}, status=500)

    @property
    def app(self) -> App:
        assert isinstance(self.server, WebServer)
        return self.server.app

    def _do_get(self) -> None:
        path, qs = self._split_path()
        if path == "/":
            html = self.app.render_index().encode("utf-8")
            self._send_bytes(html, content_type="text/html; charset=utf-8")
            return
        if path == "/debug":
            html = self.app.render_debug().encode("utf-8")
            self._send_bytes(html, content_type="text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            self._serve_static(path[len("/static/") :])
            return

        # API
        if path == "/api/config":
            status, data = self.app.api_config()
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/fs/list":
            status, data = self.app.api_fs_list(qs.get("path", ""))
            self._send_bytes(data, content_type="application/json", status=status)
            return

        if path == "/api/patches/latest":
            status, data = self.app.api_patches_latest()
            self._send_bytes(data, content_type="application/json", status=status)
            return

        if path == "/api/fs/read_text":
            status, data = self.app.api_fs_read_text(qs)
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/fs/download":
            self._api_fs_download(qs.get("path", ""))
            return
        if path == "/api/runs":
            status, data = self.app.api_runs(qs)
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/runner/tail":
            status, data = self.app.api_runner_tail(qs)
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/jobs":
            status, data = self.app.api_jobs_list()
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path.startswith("/api/jobs/") and path.endswith("/log_tail"):
            parts = path.split("/")
            if len(parts) >= 5:
                job_id = parts[3]
                status, data = self.app.api_jobs_log_tail(job_id, qs)
                self._send_bytes(data, content_type="application/json", status=status)
                return
        if path.startswith("/api/jobs/"):
            parts = path.split("/")
            if len(parts) == 4:
                job_id = parts[3]
                status, data = self.app.api_jobs_get(job_id)
                self._send_bytes(data, content_type="application/json", status=status)
                return

        if path == "/api/debug/diagnostics":
            self._send_json(self.app.diagnostics(), status=200)
            return

        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def _do_post(self) -> None:
        path, qs = self._split_path()

        if path == "/api/parse_command":
            body = self._read_json()
            status, data = self.app.api_parse_command(body)
            self._send_bytes(data, content_type="application/json", status=status)
            return

        if path == "/api/jobs/enqueue":
            body = self._read_json()
            status, data = self.app.api_jobs_enqueue(body)
            self._send_bytes(data, content_type="application/json", status=status)
            return

        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            parts = path.split("/")
            if len(parts) == 5:
                job_id = parts[3]
                status, data = self.app.api_jobs_cancel(job_id)
                self._send_bytes(data, content_type="application/json", status=status)
                return

        if path == "/api/upload/patch":
            self._api_upload_patch()
            return

        if path == "/api/fs/mkdir":
            body = self._read_json()
            status, data = self.app.api_fs_mkdir(body)
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/fs/rename":
            body = self._read_json()
            status, data = self.app.api_fs_rename(body)
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/fs/delete":
            body = self._read_json()
            status, data = self.app.api_fs_delete(body)
            self._send_bytes(data, content_type="application/json", status=status)
            return
        if path == "/api/fs/unzip":
            body = self._read_json()
            status, data = self.app.api_fs_unzip(body)
            self._send_bytes(data, content_type="application/json", status=status)
            return

        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def _split_path(self) -> tuple[str, dict[str, str]]:
        from urllib.parse import parse_qs, urlparse

        u = urlparse(self.path)
        qs_raw = parse_qs(u.query)
        qs = {k: v[0] for k, v in qs_raw.items() if v}
        return u.path, qs

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            obj = {}
        if not isinstance(obj, dict):
            return {}
        return obj

    def _send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: Any, status: int = 200) -> None:
        data = json.dumps(obj, ensure_ascii=True, indent=2).encode("utf-8")
        self._send_bytes(data, content_type="application/json", status=status)

    def _serve_static(self, rel: str) -> None:
        base = Path(__file__).resolve().parent / "static"
        p = (base / rel).resolve()
        if base not in p.parents:
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        if not p.exists() or not p.is_file():
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        ctype, _ = mimetypes.guess_type(p.name)
        if not ctype:
            ctype = "application/octet-stream"
        data = p.read_bytes()
        self._send_bytes(data, content_type=ctype)

    def _api_upload_patch(self) -> None:
        ctype = self.headers.get("Content-Type", "")
        if not ctype.startswith("multipart/form-data"):
            self._send_json({"ok": False, "error": "Expected multipart/form-data"}, status=400)
            return

        clen = self.headers.get("Content-Length")
        if clen is None:
            clen = "0"

        form = cgi.FieldStorage(
            fp=cast(IO[Any], self.rfile),
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": ctype,
                "CONTENT_LENGTH": clen,
            },
        )
        if "file" not in form:
            self._send_json({"ok": False, "error": "Missing file field"}, status=400)
            return

        field = form["file"]
        filename = os.path.basename(field.filename or "")
        data = field.file.read() if field.file else b""
        status, resp = self.app.api_upload_patch(filename, data)
        self._send_bytes(resp, content_type="application/json", status=status)

    def _api_fs_download(self, rel_path: str) -> None:
        try:
            p = self.app.jail.resolve_rel(rel_path)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)
            return
        if not p.exists() or not p.is_file():
            self._send_json({"ok": False, "error": "Not found"}, status=404)
            return
        data = p.read_bytes()
        ctype, _ = mimetypes.guess_type(p.name)
        if not ctype:
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{p.name}"')
        self.end_headers()
        self.wfile.write(data)


class WebServer(ThreadingHTTPServer):
    def __init__(self, bind: tuple[str, int], app: App) -> None:
        super().__init__(bind, WebHandler)
        self.app = app

    def server_close(self) -> None:
        try:
            self.app.shutdown()
        finally:
            super().server_close()
