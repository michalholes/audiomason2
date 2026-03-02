from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from badguys.bdg_loader import BdgAsset, BdgTest


@dataclass(frozen=True)
class MaterializedAssets:
    root: Path
    files: Dict[str, Path]


def _safe_name(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum() or ch in {"_", "-", "."}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def materialize_assets(*, repo_root: Path, issue_id: str, bdg: BdgTest) -> MaterializedAssets:
    root = repo_root / "patches" / "badguys_artifacts" / f"issue_{issue_id}" / bdg.test_id
    root.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Path] = {}
    for asset_id, asset in bdg.assets.items():
        files[asset_id] = _materialize_one(root=root, asset=asset)
    return MaterializedAssets(root=root, files=files)


def _materialize_one(*, root: Path, asset: BdgAsset) -> Path:
    safe_id = _safe_name(asset.asset_id)
    if asset.kind == "text":
        p = root / f"{safe_id}.txt"
        p.write_text(asset.content or "", encoding="utf-8")
        return p


    if asset.kind == "toml_text":
        p = root / f"{safe_id}.toml"
        p.write_text(asset.content or "", encoding="utf-8")
        return p

    if asset.kind == "python_patch_script":
        p = root / f"{safe_id}.py"
        p.write_text(asset.content or "", encoding="utf-8")
        return p


    if asset.kind == "git_patch_text":
        p = root / f"{safe_id}.patch"
        p.write_text(asset.content or "", encoding="utf-8")
        return p

    if asset.kind == "patch_zip_manifest":
        p = root / f"{safe_id}.zip"
        _write_zip_from_manifest(p, asset)
        return p

    raise SystemExit(f"FAIL: bdg: unsupported asset kind: {asset.kind}")


def _write_zip_from_manifest(path: Path, asset: BdgAsset) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Deterministic: stable ordering and fixed timestamps.
        for ent in sorted(asset.entries, key=lambda e: e.name):
            info = zipfile.ZipInfo(ent.name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, ent.content.encode("utf-8"))
    path.write_bytes(buf.getvalue())
