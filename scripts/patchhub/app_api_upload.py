from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .app_support import _err, _is_ascii, _ok


def api_upload_patch(self, filename: str, data: bytes) -> tuple[int, bytes]:
    if self.cfg.upload.ascii_only_names and not _is_ascii(filename):
        return _err("Filename must be ASCII", status=400)
    if len(data) > self.cfg.upload.max_bytes:
        return _err("File too large", status=413)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in self.cfg.upload.allowed_extensions:
        return _err("File extension not allowed", status=400)

    upload_rel = self.cfg.paths.upload_dir
    prefix = self.cfg.paths.patches_root.rstrip("/")
    if upload_rel == prefix:
        rel = ""
    elif upload_rel.startswith(prefix + "/"):
        rel = upload_rel[len(prefix) + 1 :]
    else:
        return _err("upload_dir must be under patches_root", status=500)

    upload_dir = self.jail.resolve_rel(rel)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dst = upload_dir / os.path.basename(filename)
    dst.write_bytes(data)

    rel = str(Path(self.cfg.paths.upload_dir) / dst.name)

    issue_id, commit_msg = self._derive_from_filename(dst.name)
    payload: dict[str, Any] = {"stored_rel_path": rel, "bytes": len(data)}
    if self.cfg.autofill.derive_enabled:
        payload["derived_issue"] = issue_id
        payload["derived_commit_message"] = commit_msg
    return _ok(payload)


# ---------------- UI pages ----------------
