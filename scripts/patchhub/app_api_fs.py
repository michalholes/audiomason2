from __future__ import annotations

import shutil
import zipfile
from typing import Any

from .app_support import _err, _ok, read_tail
from .fs_jail import FsJailError, list_dir, safe_rename


def api_fs_list(self, rel_path: str) -> tuple[int, bytes]:
    try:
        p = self.jail.resolve_rel(rel_path)
    except FsJailError as e:
        return _err(str(e), status=400)
    if not p.exists() or not p.is_dir():
        return _err("Not a directory", status=404)
    return _ok({"path": rel_path, "items": list_dir(p)})


def api_fs_read_text(self, qs: dict[str, str]) -> tuple[int, bytes]:
    rel = str(qs.get("path", ""))
    tail_lines_s = qs.get("tail_lines", "")
    max_bytes = int(qs.get("max_bytes", "200000"))
    max_bytes = max(1, min(max_bytes, 2000000))
    try:
        p = self.jail.resolve_rel(rel)
    except FsJailError as e:
        return _err(str(e), status=400)
    if not p.exists() or not p.is_file():
        return _err("Not a file", status=404)

    if tail_lines_s:
        tail_lines = int(tail_lines_s)
        text = read_tail(p, tail_lines)
        return _ok({"path": rel, "text": text, "truncated": False})

    # head read with truncation (byte-based)
    try:
        data = p.read_bytes()
    except Exception:
        return _err("Read failed", status=500)
    truncated = len(data) > max_bytes
    data = data[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    return _ok({"path": rel, "text": text, "truncated": truncated})


def api_fs_download(self, rel_path: str) -> tuple[int, bytes] | None:
    # handled in server layer (stream bytes)
    return None


def api_fs_mkdir(self, body: dict[str, Any]) -> tuple[int, bytes]:
    rel = str(body.get("path", ""))
    try:
        self.jail.assert_crud_allowed(rel)
        p = self.jail.resolve_rel(rel)
    except FsJailError as e:
        return _err(str(e), status=400)
    p.mkdir(parents=True, exist_ok=True)
    return _ok({"path": rel})


def api_fs_rename(self, body: dict[str, Any]) -> tuple[int, bytes]:
    src_rel = str(body.get("src", ""))
    dst_rel = str(body.get("dst", ""))
    try:
        self.jail.assert_crud_allowed(src_rel)
        self.jail.assert_crud_allowed(dst_rel)
        src = self.jail.resolve_rel(src_rel)
        dst = self.jail.resolve_rel(dst_rel)
    except FsJailError as e:
        return _err(str(e), status=400)
    if not src.exists():
        return _err("Source not found", status=404)
    safe_rename(src, dst)
    return _ok({"src": src_rel, "dst": dst_rel})


def api_fs_delete(self, body: dict[str, Any]) -> tuple[int, bytes]:
    rel = str(body.get("path", ""))
    try:
        self.jail.assert_crud_allowed(rel)
        p = self.jail.resolve_rel(rel)
    except FsJailError as e:
        return _err(str(e), status=400)
    if not p.exists():
        return _ok({"path": rel, "deleted": False})
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return _ok({"path": rel, "deleted": True})


def api_fs_unzip(self, body: dict[str, Any]) -> tuple[int, bytes]:
    zip_rel = str(body.get("zip_path", ""))
    dest_rel = str(body.get("dest_dir", ""))
    try:
        self.jail.assert_crud_allowed(zip_rel)
        self.jail.assert_crud_allowed(dest_rel)
        zip_p = self.jail.resolve_rel(zip_rel)
        dest_p = self.jail.resolve_rel(dest_rel)
    except FsJailError as e:
        return _err(str(e), status=400)
    if not zip_p.exists():
        return _err("Zip not found", status=404)
    dest_p.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_p, "r") as z:
        z.extractall(dest_p)
    return _ok({"zip_path": zip_rel, "dest_dir": dest_rel})
