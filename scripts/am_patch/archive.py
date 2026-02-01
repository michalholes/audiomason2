from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .log import Logger


def archive_patch(logger: Logger, patch_script: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / patch_script.name

    # If exists, add suffix
    if dest.exists():
        stem = dest.stem
        suf = dest.suffix
        i = 2
        while True:
            cand = dest_dir / f"{stem}_v{i}{suf}"
            if not cand.exists():
                dest = cand
                break
            i += 1

    # dest_dir is patches/successful or patches/unsuccessful; its parent is canonical patches/
    try:
        patches_dir = dest_dir.resolve().parent
        src_dir = patch_script.resolve().parent
    except Exception:
        patches_dir = dest_dir.parent
        src_dir = patch_script.parent

    # If the patch script comes from the canonical patches/ directory, move it into
    # successful/unsuccessful.
    # Otherwise (e.g. already in unsuccessful/), keep the original and copy.
    if src_dir == patches_dir:
        shutil.move(str(patch_script), str(dest))
        action = "moved"
    else:
        shutil.copy2(patch_script, dest)
        action = "copied"

    logger.section("ARCHIVE PATCH")
    logger.line(f"archived patch script ({action}) to: {dest}")
    return dest


def make_failure_zip(
    logger: Logger,
    zip_path: Path,
    *,
    workspace_repo: Path,
    log_path: Path,
    include_repo_files: list[str],
    include_patch_blobs: list[tuple[str, bytes]] | None = None,
    include_patch_paths: list[Path] | None = None,
) -> None:
    """Create patched.zip for failure/diagnostics.

    Contract:
    - Always includes the primary log under logs/<name>.
    - Includes only a subset of repo files from the workspace (changed/touched union).
    - Includes patch inputs only when requested (e.g. patch not applied, or individual failed .patch files).
    """
    logger.section("PATCHED.ZIP")
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    # De-dup, keep deterministic order.
    seen: set[str] = set()
    files: list[str] = []
    for p in include_repo_files:
        rp = p.strip().lstrip("/")
        if not rp or rp in seen:
            continue
        seen.add(rp)
        files.append(rp)
    files.sort()

    patch_blobs = include_patch_blobs or []
    patch_paths = include_patch_paths or []

    # De-dup patch entries by archive name.
    seen_patch: set[str] = set()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        if log_path.exists():
            z.write(log_path, arcname=f"logs/{log_path.name}")

        for name, data in patch_blobs:
            arc = f"patches/{Path(name).name}"
            if arc in seen_patch:
                continue
            seen_patch.add(arc)
            z.writestr(arc, data)

        for p in patch_paths:
            if not p.exists():
                continue
            arc = f"patches/{p.name}"
            if arc in seen_patch:
                continue
            seen_patch.add(arc)
            z.write(p, arcname=arc)

        for rel in files:
            src = (workspace_repo / rel).resolve()
            try:
                src.relative_to(workspace_repo.resolve())
            except Exception:
                continue
            if src.is_file():
                z.write(src, arcname=rel)

    logger.line(f"created patched.zip: {zip_path}")
