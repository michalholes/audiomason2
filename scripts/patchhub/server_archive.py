from __future__ import annotations

import os
from pathlib import Path


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
