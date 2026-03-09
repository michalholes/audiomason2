"""Import runtime stage/publish/cleanup helpers for file_io.

ASCII-only.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .service import FileService, RootName

_WORK_PREFIX = "import_runtime/work"


def normalize_relative_path(rel_path: str) -> str:
    path_text = str(rel_path).replace("\\", "/")
    if path_text.startswith("/"):
        path_text = path_text.lstrip("/")
    while "//" in path_text:
        path_text = path_text.replace("//", "/")
    if path_text == ".":
        return ""
    parts = [part for part in path_text.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError("Invalid relative_path: '..' is forbidden")
    return "/".join(parts)


def parse_root(root: RootName | str) -> RootName:
    if isinstance(root, RootName):
        return root
    return RootName(str(root))


def target_root_for_mode(mode: str) -> RootName:
    mode_text = str(mode)
    if mode_text == "stage":
        return RootName.STAGE
    if mode_text == "inplace":
        return RootName.OUTBOX
    raise ValueError("mode must be 'stage' or 'inplace'")


def default_work_relative_path(source_relative_path: str) -> str:
    rel = normalize_relative_path(source_relative_path)
    if not rel:
        return f"{_WORK_PREFIX}/root"
    return f"{_WORK_PREFIX}/{rel}"


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _copy_path(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _fallback_relative_path(fs: FileService, root: RootName, rel_path: str) -> str:
    normalized = normalize_relative_path(rel_path)
    base_path = Path(normalized)
    parent = base_path.parent
    stem = base_path.stem if base_path.suffix else base_path.name
    suffix = base_path.suffix
    index = 1
    while True:
        candidate_name = f"{stem}__{index}{suffix}" if suffix else f"{stem}__{index}"
        candidate = str(parent / candidate_name) if str(parent) != "." else candidate_name
        if not fs.exists(root, candidate):
            return candidate
        index += 1


def stage_source(
    fs: FileService,
    *,
    source_root: RootName | str,
    source_relative_path: str,
    work_relative_path: str | None = None,
) -> dict[str, dict[str, str]]:
    src_root = parse_root(source_root)
    src_rel = normalize_relative_path(source_relative_path)
    work_rel = (
        default_work_relative_path(src_rel)
        if work_relative_path is None
        else normalize_relative_path(work_relative_path)
    )

    src_abs = fs.resolve_abs_path(src_root, src_rel)
    work_abs = fs.resolve_abs_path(RootName.STAGE, work_rel)
    if not src_abs.exists():
        raise FileNotFoundError(f"Source not found: {src_root.value}:{src_rel}")

    _remove_path(work_abs)
    work_abs.parent.mkdir(parents=True, exist_ok=True)
    _copy_path(src_abs, work_abs)

    return {
        "source": {"root": src_root.value, "relative_path": src_rel},
        "work": {"root": RootName.STAGE.value, "relative_path": work_rel},
    }


def publish_staged(
    fs: FileService,
    *,
    work_relative_path: str,
    final_root: RootName | str,
    final_relative_path: str,
    overwrite: bool = False,
    cleanup: bool = True,
) -> dict[str, object]:
    work_rel = normalize_relative_path(work_relative_path)
    dst_root = parse_root(final_root)
    dst_rel = normalize_relative_path(final_relative_path)
    work_abs = fs.resolve_abs_path(RootName.STAGE, work_rel)
    if not work_abs.exists():
        raise FileNotFoundError(f"Work path not found: stage:{work_rel}")

    actual_dst_rel = dst_rel
    if fs.exists(dst_root, dst_rel):
        if overwrite:
            _remove_path(fs.resolve_abs_path(dst_root, dst_rel))
        else:
            actual_dst_rel = _fallback_relative_path(fs, dst_root, dst_rel)

    dst_abs = fs.resolve_abs_path(dst_root, actual_dst_rel)
    _remove_path(dst_abs)
    dst_abs.parent.mkdir(parents=True, exist_ok=True)
    _copy_path(work_abs, dst_abs)

    cleanup_performed = False
    if cleanup:
        _remove_path(work_abs)
        cleanup_performed = True

    return {
        "work": {"root": RootName.STAGE.value, "relative_path": work_rel},
        "final": {"root": dst_root.value, "relative_path": actual_dst_rel},
        "cleanup_performed": cleanup_performed,
    }


def publish_for_mode(
    fs: FileService,
    *,
    work_relative_path: str,
    final_relative_path: str,
    mode: str,
    overwrite: bool = False,
    cleanup: bool = True,
) -> dict[str, object]:
    return publish_staged(
        fs,
        work_relative_path=work_relative_path,
        final_root=target_root_for_mode(mode),
        final_relative_path=final_relative_path,
        overwrite=overwrite,
        cleanup=cleanup,
    )


def cleanup_stage(fs: FileService, *, work_relative_path: str) -> None:
    work_rel = normalize_relative_path(work_relative_path)
    _remove_path(fs.resolve_abs_path(RootName.STAGE, work_rel))
