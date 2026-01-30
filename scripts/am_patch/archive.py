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


def make_patched_zip(
    logger: Logger,
    zip_path: Path,
    include_dir: Path,
    log_path: Path,
    used_patch: Path | None = None,
) -> None:
    logger.section("PATCHED.ZIP")
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    excluded_dir_names = {
        ".git",
        "venv",
        ".venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        "oldlogs",
    }

    def is_excluded(rel: Path) -> bool:
        if rel.suffix == ".pyc":
            return True
        for part in rel.parts:
            if part in excluded_dir_names:
                return True
        return False

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # include log
        if log_path.exists():
            z.write(log_path, arcname=f"logs/{log_path.name}")

        # include used patch script (best effort)
        if used_patch is not None and used_patch.exists():
            z.write(used_patch, arcname=f"patches/{used_patch.name}")

        # include workspace (best effort)
        if include_dir.exists():
            for p in include_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(include_dir)
                    if is_excluded(rel):
                        continue
                    z.write(p, arcname=str(Path("workspace") / rel))
    logger.line(f"created patched.zip: {zip_path}")
