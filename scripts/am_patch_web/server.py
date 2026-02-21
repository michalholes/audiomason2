from __future__ import annotations

import cgi
import json
import mimetypes
import os
import time
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

        if path.startswith("/api/jobs/") and path.endswith("/events"):
            parts = path.split("/")
            if len(parts) == 5:
                job_id = parts[3]
                self._api_jobs_events(job_id)
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

        if path == "/api/fs/archive":
            self._api_fs_archive()
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

    def _api_jobs_events(self, job_id: str) -> None:
        job = self.app.queue.get_job(job_id)

        disk_job = None
        if job is None:
            disk_job = self.app._load_job_from_disk(job_id)

        if job is None and disk_job is None:
            # Do not return 404: EventSource will retry forever.
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            data = json.dumps({"reason": "job_not_found"}, ensure_ascii=True)
            self.wfile.write(f"event: end\ndata: {data}\n\n".encode())
            self.wfile.flush()
            return

        if disk_job is not None and job is None:
            jsonl_path = self.app._job_jsonl_path_from_fields(
                job_id=str(job_id),
                mode=str(disk_job.mode),
                issue_id=str(disk_job.issue_id),
            )
        else:
            assert job is not None
            jsonl_path = self.app._job_jsonl_path(job)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send_line(line: str) -> None:
            self.wfile.write(line.encode("utf-8", errors="replace"))
            self.wfile.flush()

        def send_end(reason: str, status: str | None = None) -> None:
            payload: dict[str, Any] = {"reason": reason}
            if status is not None:
                payload["status"] = status
            data = json.dumps(payload, ensure_ascii=True)
            send_line("event: end\n")
            send_line("data: " + data + "\n\n")

        last_ping = time.monotonic()
        offset = 0
        last_growth = time.monotonic()

        while True:
            try:
                # Wait for the JSONL file to appear (runner creates it early, but not instantly).
                if not jsonl_path.exists():
                    job_now = self.app.queue.get_job(job_id)
                    if job_now is None:
                        if disk_job is not None:
                            send_end("job_completed", status=str(disk_job.status))
                            return
                        send_end("job_not_found")
                        return
                    if job_now.status != "running":
                        send_end("job_completed", status=str(job_now.status))
                        return
                    time.sleep(0.2)
                    continue

                with jsonl_path.open("rb") as fp:
                    fp.seek(offset)
                    chunk = fp.read()
                    if chunk:
                        last_growth = time.monotonic()
                        # We only emit complete lines. Keep partial trailing bytes for next pass.
                        parts = chunk.split(b"\n")
                        if chunk.endswith(b"\n"):
                            complete = parts[:-1]
                            tail = b""
                        else:
                            complete = parts[:-1]
                            tail = parts[-1]
                        for raw in complete:
                            raw = raw.strip()
                            if not raw:
                                continue
                            try:
                                s = raw.decode("utf-8")
                            except Exception:
                                s = raw.decode("utf-8", errors="replace")
                            send_line(f"data: {s}\n\n")
                        offset = fp.tell() - len(tail)

                now = time.monotonic()
                if now - last_ping >= 10.0:
                    send_line(": ping\n\n")
                    last_ping = now

                job_now = self.app.queue.get_job(job_id)
                if job_now is None:
                    if disk_job is not None:
                        send_end("job_completed", status=str(disk_job.status))
                        return
                    send_end("job_not_found")
                    return

                if job_now.status != "running" and now - last_growth >= 0.5:
                    # If nothing new has arrived shortly after completion, end the stream.
                    send_end("job_completed", status=str(job_now.status))
                    return

                time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                return
            except FileNotFoundError:
                # The JSONL file may be rotated/removed; end deterministically.
                job_now = self.app.queue.get_job(job_id)
                if job_now is not None:
                    send_end("job_completed", status=str(job_now.status))
                elif disk_job is not None:
                    send_end("job_completed", status=str(disk_job.status))
                else:
                    send_end("io_error")
                return
            except OSError:
                send_end("io_error")
                return

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

    def _api_fs_archive(self) -> None:
        body = self._read_json()
        paths = body.get("paths")
        if not isinstance(paths, list) or not paths:
            self._send_json({"ok": False, "error": "paths must be a non-empty list"}, status=400)
            return

        # Deterministic ordering
        rel_paths = []
        for x in paths:
            if not isinstance(x, str):
                continue
            rel = x.strip().lstrip("/")
            if rel:
                rel_paths.append(rel)
        if not rel_paths:
            self._send_json({"ok": False, "error": "No valid paths"}, status=400)
            return
        rel_paths = sorted(set(rel_paths))

        try:
            files = self._collect_zip_files(rel_paths)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        data = self._build_zip_bytes(files)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", 'attachment; filename="selection.zip"')
        self.end_headers()
        self.wfile.write(data)

    def _collect_zip_files(self, rel_paths: list[str]) -> list[tuple[str, Path]]:
        out: list[tuple[str, Path]] = []
        seen: set[str] = set()
        for rel in rel_paths:
            p = self.app.jail.resolve_rel(rel)
            if not p.exists():
                raise ValueError(f"Not found: {rel}")
            if p.is_file():
                arc = rel
                if arc not in seen:
                    out.append((arc, p))
                    seen.add(arc)
                continue

            # Directory: walk deterministically
            root = p
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames.sort()
                filenames.sort()
                dp = Path(dirpath)
                for fn in filenames:
                    fp = dp / fn
                    if not fp.is_file():
                        continue
                    sub_rel = str(fp.relative_to(self.app.jail.patches_root()))
                    sub_rel = sub_rel.replace(os.sep, "/")
                    if sub_rel not in seen:
                        out.append((sub_rel, fp))
                        seen.add(sub_rel)

        out.sort(key=lambda t: t[0])
        return out

    def _build_zip_bytes(self, files: list[tuple[str, Path]]) -> bytes:
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for arc, fp in files:
                # zipfile expects forward slashes
                arc = arc.replace(os.sep, "/")
                z.write(fp, arcname=arc)
        return buf.getvalue()


class WebServer(ThreadingHTTPServer):
    def __init__(self, bind: tuple[str, int], app: App) -> None:
        super().__init__(bind, WebHandler)
        self.app = app

    def server_close(self) -> None:
        try:
            self.app.shutdown()
        finally:
            super().server_close()
