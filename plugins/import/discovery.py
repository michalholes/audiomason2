"""Deterministic discovery (PHASE 0) for import wizard engine.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass

from plugins.file_io.service import FileEntry, FileService, RootName

_BUNDLE_EXTS = {
    ".zip",
    ".tar",
    ".tgz",
    ".tar.gz",
    ".tar.bz2",
}


def _normalize_rel_path(rel_path: str) -> str:
    # file_io already enforces jail semantics for operations, but discovery artifacts
    # must be clean and canonical.
    p = rel_path.replace("\\", "/")
    if p.startswith("/"):
        p = p.lstrip("/")
    # Collapse consecutive slashes.
    while "//" in p:
        p = p.replace("//", "/")

    # Normalize '.' to empty string.
    if p == ".":
        p = ""

    segments = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in segments):
        raise ValueError("Invalid relative_path: '..' is forbidden")

    return "/".join(segments)


def _kind(entry: FileEntry) -> str:
    if entry.is_dir:
        return "dir"
    name = entry.rel_path.lower()
    for ext in sorted(_BUNDLE_EXTS, key=len, reverse=True):
        if name.endswith(ext):
            return "bundle"
    return "file"


@dataclass(frozen=True)
class DiscoveryItem:
    item_id: str
    root: str
    relative_path: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {
            "item_id": self.item_id,
            "root": self.root,
            "relative_path": self.relative_path,
            "kind": self.kind,
        }


def run_discovery(fs: FileService, *, root: str, relative_path: str) -> list[dict[str, str]]:
    root_enum = RootName(root)
    base_rel = _normalize_rel_path(relative_path)

    entries = fs.list_dir(root_enum, base_rel or ".", recursive=True)

    items: list[DiscoveryItem] = []
    for e in entries:
        rel_norm = _normalize_rel_path(e.rel_path)
        items.append(
            DiscoveryItem(
                item_id=f"root:{root}|path:{rel_norm}",
                root=root,
                relative_path=rel_norm,
                kind=_kind(e),
            )
        )

    # Canonical ordering: root, relative_path, kind
    items_sorted = sorted(items, key=lambda it: (it.root, it.relative_path, it.kind))
    return [it.to_dict() for it in items_sorted]
