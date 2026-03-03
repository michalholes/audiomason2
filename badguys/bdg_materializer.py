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


def _subst_content(content: str, *, issue_id: str) -> str:
    return content.replace("${issue_id}", str(issue_id))


def materialize_assets(*, repo_root: Path, issue_id: str, bdg: BdgTest) -> MaterializedAssets:
    root = repo_root / "patches" / "badguys_artifacts" / f"issue_{issue_id}" / bdg.test_id
    root.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Path] = {}
    for asset_id, asset in bdg.assets.items():
        files[asset_id] = _materialize_one(root=root, repo_root=repo_root, issue_id=issue_id, test_id=bdg.test_id, asset=asset)
    return MaterializedAssets(root=root, files=files)


def _materialize_one(*, root: Path, repo_root: Path, issue_id: str, test_id: str, asset: BdgAsset) -> Path:
    safe_id = _safe_name(asset.asset_id)
    if asset.kind == "text":
        p = root / f"{safe_id}.txt"
        p.write_text(_subst_content(asset.content or "", issue_id=issue_id), encoding="utf-8")
        return p

    if asset.kind == "toml_text":
        p = root / f"{safe_id}.toml"
        p.write_text(_subst_content(asset.content or "", issue_id=issue_id), encoding="utf-8")
        return p

    if asset.kind == "python_patch_script":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{issue_id}__bdg__{safe_test}__{safe_id}.py"
        p.write_text(_subst_content(asset.content or "", issue_id=issue_id), encoding="utf-8")
        return p

    if asset.kind == "git_patch_text":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{issue_id}__bdg__{safe_test}__{safe_id}.patch"
        p.write_text(_subst_content(asset.content or "", issue_id=issue_id), encoding="utf-8")
        return p

    if asset.kind == "patch_zip_manifest":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{issue_id}__bdg__{safe_test}__{safe_id}.zip"
        _write_zip_from_manifest(p, issue_id=issue_id, asset=asset)
        return p

    raise SystemExit(f"FAIL: bdg: unsupported asset kind: {asset.kind}")


def _write_zip_from_manifest(path: Path, *, issue_id: str, asset: BdgAsset) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Deterministic: stable ordering and fixed timestamps.
        for ent in sorted(asset.entries, key=lambda e: e.name):
            info = zipfile.ZipInfo(ent.name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = _subst_content(ent.content, issue_id=issue_id).encode("utf-8")
            z.writestr(info, data)
    path.write_bytes(buf.getvalue())
