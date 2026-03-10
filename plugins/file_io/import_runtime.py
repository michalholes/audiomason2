"""Import runtime stage/publish/cleanup helpers for file_io.

ASCII-only.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from audiomason.core.errors import FileError

from .service import ArchiveFormat, ArchiveService, FileService, RootName

_WORK_PREFIX = "import_runtime/work"
_ARCHIVE_SUFFIXES: dict[ArchiveFormat, tuple[str, ...]] = {
    ArchiveFormat.TAR_GZ: (".tar.gz", ".tgz"),
    ArchiveFormat.TAR_XZ: (".tar.xz", ".txz"),
    ArchiveFormat.TAR: (".tar",),
    ArchiveFormat.ZIP: (".zip",),
    ArchiveFormat.RAR: (".rar",),
    ArchiveFormat.SEVEN_Z: (".7z",),
}


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


def _strip_archive_suffix(source_relative_path: str, archive_format: ArchiveFormat | None) -> str:
    rel = normalize_relative_path(source_relative_path)
    if archive_format is None or not rel:
        return rel
    lower_rel = rel.lower()
    for suffix in _ARCHIVE_SUFFIXES.get(archive_format, ()):
        if lower_rel.endswith(suffix):
            return rel[: -len(suffix)]
    return rel


def default_work_relative_path(
    source_relative_path: str,
    *,
    source_kind: str = "path",
    archive_format: ArchiveFormat | None = None,
) -> str:
    rel = normalize_relative_path(source_relative_path)
    if source_kind == "archive":
        rel = _strip_archive_suffix(rel, archive_format)
    if not rel:
        return f"{_WORK_PREFIX}/root"
    return f"{_WORK_PREFIX}/{rel}"


def inspect_source(
    fs: FileService,
    *,
    source_root: RootName | str,
    source_relative_path: str,
    archive_service: ArchiveService | None = None,
) -> dict[str, str]:
    src_root = parse_root(source_root)
    src_rel = normalize_relative_path(source_relative_path)
    src_abs = fs.resolve_abs_path(src_root, src_rel)
    if not src_abs.exists():
        raise FileNotFoundError(f"Source not found: {src_root.value}:{src_rel}")

    if src_abs.is_dir():
        return {
            "root": src_root.value,
            "relative_path": src_rel,
            "kind": "dir",
            "archive_format": "",
        }

    archive_format = ""
    source_kind = "file"
    archive_service = archive_service or ArchiveService(fs)
    try:
        detected = archive_service.detect_format(src_root, src_rel)
    except FileError:
        detected = None
    if detected is not None:
        source_kind = "archive"
        archive_format = detected.format.value

    return {
        "root": src_root.value,
        "relative_path": src_rel,
        "kind": source_kind,
        "archive_format": archive_format,
    }


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
    archive_service: ArchiveService | None = None,
) -> dict[str, dict[str, str]]:
    src_root = parse_root(source_root)
    src_rel = normalize_relative_path(source_relative_path)
    intake = inspect_source(
        fs,
        source_root=src_root,
        source_relative_path=src_rel,
        archive_service=archive_service,
    )
    archive_service = archive_service or ArchiveService(fs)
    detected_format = ArchiveFormat(intake["archive_format"]) if intake["archive_format"] else None
    work_rel = (
        default_work_relative_path(
            src_rel,
            source_kind=intake["kind"],
            archive_format=detected_format,
        )
        if work_relative_path is None
        else normalize_relative_path(work_relative_path)
    )

    fs.delete_path(RootName.STAGE, work_rel, missing_ok=True)
    if intake["kind"] == "archive":
        archive_service.unpack(
            src_root,
            src_rel,
            RootName.STAGE,
            work_rel,
            autodetect=True,
            preserve_tree=True,
            flatten=False,
        )
    else:
        fs.copy_path(src_root, src_rel, RootName.STAGE, work_rel, overwrite=True)

    return {
        "source": {"root": src_root.value, "relative_path": src_rel},
        "work": {"root": RootName.STAGE.value, "relative_path": work_rel},
        "intake": {"kind": intake["kind"], "archive_format": intake["archive_format"]},
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
            fs.delete_path(dst_root, dst_rel, missing_ok=True)
        else:
            actual_dst_rel = _fallback_relative_path(fs, dst_root, dst_rel)

    fs.copy_path(RootName.STAGE, work_rel, dst_root, actual_dst_rel, overwrite=True)

    cleanup_performed = False
    if cleanup:
        fs.delete_path(RootName.STAGE, work_rel, missing_ok=True)
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
    fs.delete_path(RootName.STAGE, work_rel, missing_ok=True)
