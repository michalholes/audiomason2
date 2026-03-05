from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from badguys.bdg_loader import BdgAsset, BdgTest
from badguys.bdg_subst import SubstCtx, subst_text


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


def materialize_assets(*, repo_root: Path, subst: SubstCtx, bdg: BdgTest) -> MaterializedAssets:
    root = repo_root / "patches" / "badguys_artifacts" / f"issue_{subst.issue_id}" / bdg.test_id
    root.mkdir(parents=True, exist_ok=True)
    files: Dict[str, Path] = {}
    for asset_id, asset in bdg.assets.items():
        files[asset_id] = _materialize_one(
            root=root,
            repo_root=repo_root,
            subst=subst,
            test_id=bdg.test_id,
            asset=asset,
        )
    return MaterializedAssets(root=root, files=files)


def _materialize_one(
    *,
    root: Path,
    repo_root: Path,
    subst: SubstCtx,
    test_id: str,
    asset: BdgAsset,
) -> Path:
    safe_id = _safe_name(asset.asset_id)
    if asset.kind == "text":
        p = root / f"{safe_id}.txt"
        p.write_text(subst_text(asset.content or "", ctx=subst), encoding="utf-8")
        return p

    if asset.kind == "toml_text":
        p = root / f"{safe_id}.toml"
        p.write_text(subst_text(asset.content or "", ctx=subst), encoding="utf-8")
        return p

    if asset.kind == "python_patch_script":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{subst.issue_id}__bdg__{safe_test}__{safe_id}.py"
        p.write_text(subst_text(asset.content or "", ctx=subst), encoding="utf-8")
        return p

    if asset.kind == "git_patch_text":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{subst.issue_id}__bdg__{safe_test}__{safe_id}.patch"
        p.write_text(subst_text(asset.content or "", ctx=subst), encoding="utf-8")
        return p

    if asset.kind == "patch_zip_manifest":
        patches_dir = repo_root / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        safe_test = _safe_name(test_id)
        p = patches_dir / f"issue_{subst.issue_id}__bdg__{safe_test}__{safe_id}.zip"
        _write_zip_from_manifest(p, subst=subst, asset=asset)
        return p

    raise SystemExit(f"FAIL: bdg: unsupported asset kind: {asset.kind}")


def _write_zip_from_manifest(path: Path, *, subst: SubstCtx, asset: BdgAsset) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Deterministic: stable ordering and fixed timestamps.
        for ent in sorted(asset.entries, key=lambda e: subst_text(e.name, ctx=subst)):
            name = subst_text(ent.name, ctx=subst)
            info = zipfile.ZipInfo(name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = subst_text(ent.content, ctx=subst).encode("utf-8")
            z.writestr(info, data)
    path.write_bytes(buf.getvalue())
