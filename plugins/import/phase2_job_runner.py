"""Plugin-owned PHASE 2 runner for canonical import job requests.

ASCII-only.
"""

from __future__ import annotations

import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol, TypeGuard, cast

from plugins.file_io.import_runtime import normalize_relative_path, publish_staged, stage_source
from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .cover_boundary import apply_cover_candidate as apply_cover_candidate_ref
from .engine_util import emit_required_event
from .file_io_boundary import materialize_local_path
from .storage import read_json


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [dict(item) for item in value if _is_str_object_dict(item)]


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


class _PluginLoader(Protocol):
    def get_plugin(self, name: str) -> object: ...


class _SupportsFileService(Protocol):
    def get_file_service(self) -> FileService: ...


class _AudioProcessorPlugin(Protocol):
    bitrate: str
    loudnorm: bool
    split_chapters: bool

    def plan_import_conversion(
        self,
        source_file: Path,
        output_dir: Path,
        *,
        chapters: list[dict[str, object]] | None,
    ) -> object: ...

    pass


class _CoverHandlerPlugin(Protocol):
    async def download_cover(self, url: str, *, output_dir: Path) -> Path: ...

    async def convert_to_jpeg(self, cover_path: Path) -> Path: ...

    async def embed_covers_batch(self, mp3_files: list[Path], cover_path: Path) -> None: ...


class _Id3TaggerPlugin(Protocol):
    async def write_tags(
        self,
        mp3_file: Path,
        tag_payload: dict[str, object],
        *,
        wipe_before_write: bool,
        preserve_cover: bool,
        file_index: int,
    ) -> None: ...


_AUDIO_SUFFIXES = {".m4a", ".m4b", ".mp3", ".opus"}
_CHAPTER_SUFFIXES = {".m4a", ".m4b"}
_ARCHIVE_SUFFIXES = (
    ".tar.bz2",
    ".tar.gz",
    ".tar",
    ".tgz",
    ".zip",
    ".rar",
    ".7z",
)


def _parse_job_requests_path(text: str) -> tuple[RootName, str]:
    root_text, rel_path = text.split(":", 1)
    root = RootName(root_text.strip())
    rel = normalize_relative_path(rel_path.strip())
    if not rel:
        raise ValueError("job_requests_path must include a relative path")
    return root, rel


def _remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _is_archive_segment(text: str) -> bool:
    lower = text.lower()
    return any(lower.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _split_virtual_archive_source_rel(source_rel: str) -> tuple[str, str] | None:
    parts = [part for part in normalize_relative_path(source_rel).split("/") if part]
    for index, part in enumerate(parts):
        if not _is_archive_segment(part):
            continue
        if index + 1 >= len(parts):
            return None
        archive_rel = "/".join(parts[: index + 1])
        inside_rel = "/".join(parts[index + 1 :])
        if inside_rel:
            return archive_rel, inside_rel
        return None
    return None


def _iter_audio_sources(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in _AUDIO_SUFFIXES else []
    files = [
        path
        for path in sorted(source_path.rglob("*"))
        if path.is_file() and path.suffix.lower() in _AUDIO_SUFFIXES
    ]
    return files


def _iter_work_files(work_path: Path) -> list[Path]:
    if not work_path.exists():
        return []
    return [path for path in sorted(work_path.rglob("*")) if path.is_file()]


def _rename_authority(action: dict[str, object]) -> dict[str, object]:
    authority = _as_str_object_dict(action.get("authority"))
    rename = _as_str_object_dict(authority.get("rename"))
    mode = str(rename.get("mode") or "")
    if mode == "keep_generated":
        extension = str(rename.get("extension") or "").strip().lower()
        if not extension.startswith(".") or len(extension) < 2:
            raise ValueError("keep_generated extension is required")
        return {"mode": mode, "extension": extension}
    if mode == "explicit_relative_paths":
        outputs_any = rename.get("outputs")
        outputs_raw = outputs_any if _is_object_list(outputs_any) else []
        outputs: list[str] = []
        for item in outputs_raw:
            if not isinstance(item, str):
                continue
            rel_path = normalize_relative_path(item)
            if rel_path and rel_path not in outputs:
                outputs.append(rel_path)
        if not outputs:
            raise ValueError("explicit_relative_paths outputs are required")
        return {"mode": mode, "outputs": outputs}
    raise ValueError("action authority.rename is required")


def _apply_rename_authority(*, work_path: Path, action: dict[str, object]) -> None:
    rename = _rename_authority(action)
    produced = _iter_work_files(work_path)
    if not produced:
        raise ValueError("audio.import produced no outputs")

    if rename["mode"] == "keep_generated":
        extension = str(rename["extension"])
        mismatched = [
            normalize_relative_path(str(path.relative_to(work_path)))
            for path in produced
            if path.suffix.lower() != extension
        ]
        if mismatched:
            raise ValueError(
                f"keep_generated extension mismatch: expected {extension}, got {mismatched}"
            )
        return

    outputs = _as_str_list(rename.get("outputs"))
    if len(produced) != len(outputs):
        raise ValueError(
            f"explicit_relative_paths count mismatch: expected {len(outputs)}, got {len(produced)}"
        )

    temp_paths: list[tuple[Path, str]] = []
    for index, source_path in enumerate(produced, start=1):
        temp_path = work_path / f".am2_rename_tmp_{index:04d}{source_path.suffix.lower() or '.tmp'}"
        if temp_path.exists():
            raise ValueError(f"rename temp path already exists: {temp_path.name}")
        source_path.rename(temp_path)
        temp_paths.append((temp_path, outputs[index - 1]))

    for temp_path, rel_path in temp_paths:
        final_path = work_path / rel_path
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.rename(final_path)


def _iter_mp3_outputs(work_path: Path) -> list[Path]:
    if not work_path.exists():
        return []
    return [path for path in sorted(work_path.rglob("*.mp3")) if path.is_file()]


def _metadata_authority_values(action: dict[str, object]) -> dict[str, str]:
    authority = _as_str_object_dict(action.get("authority"))
    meta = _as_str_object_dict(authority.get("metadata_tags"))
    values = _as_str_object_dict(meta.get("values"))
    return {
        str(key): str(value)
        for key, value in values.items()
        if str(key) and isinstance(value, str) and value
    }


def _ordered_capabilities(action: dict[str, object]) -> list[dict[str, object]]:
    caps_any = action.get("capabilities")
    if not _is_object_list(caps_any):
        return []
    caps = [dict(cap) for cap in caps_any if _is_str_object_dict(cap)]
    authority_values = _metadata_authority_values(action)
    for cap in caps:
        if str(cap.get("kind") or "") != "metadata.tags":
            continue
        values = _as_str_object_dict(cap.get("values"))
        if values or not authority_values:
            continue
        cap["values"] = dict(authority_values)

    def _capability_sort_key(item: dict[str, object]) -> tuple[int, str]:
        return (_to_int_or_default(item.get("order"), 0), str(item.get("kind") or ""))

    return sorted(caps, key=_capability_sort_key)


def _resolve_work_relative_path(job_id: str, action_index: int, target_rel: str) -> str:
    suffix = normalize_relative_path(target_rel) or "root"
    return normalize_relative_path(f"import/process_runtime/{job_id}/{action_index:04d}/{suffix}")


def _detect_chapters(
    plugin: object,
    source_file: Path,
) -> list[dict[str, object]] | Awaitable[list[dict[str, object]] | None] | None:
    detector = cast(object, getattr(plugin, "_detect_chapters", None))
    if not callable(detector):
        return None
    detect_fn = cast(
        Callable[
            [Path],
            list[dict[str, object]] | Awaitable[list[dict[str, object]] | None] | None,
        ],
        detector,
    )
    return detect_fn(source_file)


def _execute_plan(plugin: object, plan: object) -> object:
    execute = cast(object, getattr(plugin, "_execute_plan", None))
    if not callable(execute):
        raise ValueError("audio_processor._execute_plan is required")
    execute_fn = cast(Callable[[object], object], execute)
    return execute_fn(plan)


async def _run_audio_import(
    *,
    fs: FileService,
    plugin_loader: _PluginLoader,
    source_root: RootName,
    source_rel: str,
    source_path: Path,
    work_path: Path,
    job_id: str,
    action_index: int,
    capability: dict[str, object],
) -> None:
    plugin_raw = plugin_loader.get_plugin("audio_processor")
    plugin = cast(_AudioProcessorPlugin, plugin_raw)
    options = _as_str_object_dict(capability.get("options"))

    original_bitrate = plugin.bitrate
    original_loudnorm = plugin.loudnorm
    original_split_chapters = plugin.split_chapters
    if "bitrate" in options:
        plugin.bitrate = str(options["bitrate"])
    if "loudnorm" in options:
        plugin.loudnorm = bool(options["loudnorm"])
    if "split_chapters" in options:
        plugin.split_chapters = bool(options["split_chapters"])

    work_path.mkdir(parents=True, exist_ok=True)
    staged_source_rel: str | None = None
    effective_source_path = source_path
    virtual_archive = _split_virtual_archive_source_rel(source_rel)
    if virtual_archive is not None:
        archive_rel, archive_inside_rel = virtual_archive
        staged_source_rel = normalize_relative_path(
            f"import/process_runtime/{job_id}/{action_index:04d}/_source"
        )
        stage_source(
            fs,
            source_root=source_root,
            source_relative_path=archive_rel,
            work_relative_path=staged_source_rel,
        )
        extracted_root = materialize_local_path(fs, RootName.STAGE, staged_source_rel)
        effective_source_path = extracted_root / Path(
            *[part for part in archive_inside_rel.split("/") if part]
        )
    elif source_path.is_file() and source_path.suffix.lower() not in _AUDIO_SUFFIXES:
        staged_source_rel = normalize_relative_path(
            f"import/process_runtime/{job_id}/{action_index:04d}/_source"
        )
        stage_source(
            fs,
            source_root=source_root,
            source_relative_path=source_rel,
            work_relative_path=staged_source_rel,
        )
        effective_source_path = materialize_local_path(fs, RootName.STAGE, staged_source_rel)
    if not effective_source_path.exists():
        effective_source_path_norm = normalize_relative_path(str(effective_source_path))
        raise ValueError(f"source path missing after staging: {effective_source_path_norm}")
    try:
        for source_file in _iter_audio_sources(effective_source_path):
            relative_parent = (
                source_file.relative_to(effective_source_path).parent
                if effective_source_path.is_dir()
                else Path()
            )
            output_dir = work_path / relative_parent
            output_dir.mkdir(parents=True, exist_ok=True)
            chapters: list[dict[str, object]] | None = None
            if plugin.split_chapters and source_file.suffix.lower() in _CHAPTER_SUFFIXES:
                detected = _detect_chapters(plugin_raw, source_file)
                if isinstance(detected, Awaitable):
                    detected_resolved = await detected
                    chapters = _as_dict_list(detected_resolved)
                elif _is_object_list(detected):
                    chapters = _as_dict_list(detected)
            plan = plugin.plan_import_conversion(source_file, output_dir, chapters=chapters)
            execute_result = _execute_plan(plugin_raw, plan)
            if isinstance(execute_result, Awaitable):
                await execute_result
    finally:
        if staged_source_rel is not None:
            fs.delete_path(RootName.STAGE, staged_source_rel, missing_ok=True)
        plugin.bitrate = original_bitrate
        plugin.loudnorm = original_loudnorm
        plugin.split_chapters = original_split_chapters


async def _run_cover_embed(
    *,
    fs: FileService,
    plugin_loader: _PluginLoader,
    source_root: RootName,
    source_relative_path: str,
    work_rel: str,
    work_path: Path,
    capability: dict[str, object],
) -> None:
    plugin = cast(_CoverHandlerPlugin, plugin_loader.get_plugin("cover_handler"))
    mode = str(capability.get("mode") or "skip")
    if mode == "skip":
        return

    cover_path: Path | None = None
    if mode in {"file", "embedded", "copy", "extract_embedded", "download"}:
        candidate = _as_str_object_dict(capability.get("candidate"))
        if candidate:
            if "source_root" not in candidate:
                candidate["source_root"] = source_root.value
            if "source_relative_path" not in candidate:
                candidate["source_relative_path"] = source_relative_path
            if str(candidate.get("apply_mode") or "") == "copy" and not str(
                candidate.get("candidate_relative_path") or ""
            ):
                candidate_path = normalize_relative_path(str(candidate.get("path") or ""))
                if candidate_path:
                    candidate["candidate_relative_path"] = candidate_path
            if str(candidate.get("apply_mode") or "") == "extract_embedded" and not str(
                candidate.get("audio_relative_path") or ""
            ):
                audio_path = normalize_relative_path(str(candidate.get("path") or ""))
                if audio_path:
                    candidate["audio_relative_path"] = audio_path
            materialized_ref = await apply_cover_candidate_ref(
                fs=fs,
                candidate=candidate,
                output_root=RootName.STAGE,
                output_relative_dir=work_rel,
                plugin=plugin,
            )
            if materialized_ref is not None:
                cover_path = materialize_local_path(
                    fs,
                    RootName(str(materialized_ref["root"])),
                    str(materialized_ref["relative_path"]),
                )
    elif mode == "url":
        url = str(capability.get("url") or "")
        if url:
            cover_path = await plugin.download_cover(url, output_dir=work_path)

    if cover_path is None:
        return

    cover_path = await plugin.convert_to_jpeg(cover_path)
    mp3_files = _iter_mp3_outputs(work_path)
    if not mp3_files:
        return
    await plugin.embed_covers_batch(mp3_files, cover_path)


async def _run_metadata_tags(
    *,
    plugin_loader: _PluginLoader,
    work_path: Path,
    capability: dict[str, object],
) -> None:
    plugin = cast(_Id3TaggerPlugin, plugin_loader.get_plugin("id3_tagger"))
    values = _as_str_object_dict(capability.get("values"))
    track_start = capability.get("track_start")
    if not values and track_start is None:
        return
    wipe_before_write = bool(capability.get("wipe_before_write", True))
    preserve_cover = bool(capability.get("preserve_cover", True))
    tag_payload = dict(capability)
    for file_index, mp3_file in enumerate(_iter_mp3_outputs(work_path)):
        await plugin.write_tags(
            mp3_file,
            tag_payload,
            wipe_before_write=wipe_before_write,
            preserve_cover=preserve_cover,
            file_index=file_index,
        )


async def _run_publish_write(
    *,
    fs: FileService,
    work_rel: str,
    capability: dict[str, object],
) -> None:
    root = RootName(str(capability.get("root") or RootName.STAGE.value))
    rel = normalize_relative_path(str(capability.get("relative_path") or ""))
    if not rel:
        raise ValueError("publish.write.relative_path must be non-empty")
    publish_staged(
        fs,
        work_relative_path=work_rel,
        final_root=root,
        final_relative_path=rel,
        overwrite=bool(capability.get("overwrite", False)),
        cleanup=True,
    )


async def _run_source_delete(*, source_path: Path, capability: dict[str, object]) -> None:
    if bool(capability.get("enabled", False)):
        _remove_path(source_path)


async def run_phase2_job_requests(
    *,
    engine: _SupportsFileService,
    job_id: str,
    job_meta: dict[str, object],
    plugin_loader: _PluginLoader,
) -> None:
    fs = engine.get_file_service()
    job_requests_path = str(job_meta.get("job_requests_path") or "")
    if not job_requests_path:
        raise ValueError("job_requests_path is required")

    root, rel_path = _parse_job_requests_path(job_requests_path)
    job_requests_any = read_json(fs, root, rel_path)
    if not _is_str_object_dict(job_requests_any):
        raise ValueError("job_requests.json is invalid")

    actions = _as_dict_list(job_requests_any.get("actions"))
    diagnostics_context = _as_str_object_dict(job_requests_any.get("diagnostics_context"))

    emit_required_event(
        "phase2.runner.start",
        "phase2.runner.start",
        {
            "job_id": job_id,
            "batch_size": len(actions),
            **diagnostics_context,
        },
    )

    for action_index, action in enumerate(actions, start=1):
        if str(action.get("type") or "") != "import.book":
            continue
        source_any = action.get("source")
        target_any = action.get("target")
        if not _is_str_object_dict(source_any) or not _is_str_object_dict(target_any):
            raise ValueError("action source/target must be objects")
        source_root = RootName(str(source_any.get("root") or ""))
        source_rel = normalize_relative_path(str(source_any.get("relative_path") or ""))
        target_rel = normalize_relative_path(str(target_any.get("relative_path") or ""))
        if not source_rel or not target_rel:
            raise ValueError("action source/target paths must be non-empty")

        source_path = materialize_local_path(fs, source_root, source_rel)
        work_rel = _resolve_work_relative_path(job_id, action_index, target_rel)
        work_path = materialize_local_path(fs, RootName.STAGE, work_rel)
        _remove_path(work_path)
        work_path.mkdir(parents=True, exist_ok=True)

        emit_required_event(
            "phase2.action.start",
            "phase2.action.start",
            {
                "job_id": job_id,
                "action_index": action_index,
                "book_id": str(action.get("book_id") or ""),
                "source_relative_path": source_rel,
                "target_relative_path": target_rel,
                **diagnostics_context,
            },
        )

        for capability in _ordered_capabilities(action):
            kind = str(capability.get("kind") or "")
            if kind == "audio.import":
                await _run_audio_import(
                    fs=fs,
                    plugin_loader=plugin_loader,
                    source_root=source_root,
                    source_rel=source_rel,
                    source_path=source_path,
                    work_path=work_path,
                    job_id=job_id,
                    action_index=action_index,
                    capability=capability,
                )
                _apply_rename_authority(work_path=work_path, action=action)
                continue
            if kind == "cover.embed":
                await _run_cover_embed(
                    fs=fs,
                    plugin_loader=plugin_loader,
                    source_root=source_root,
                    source_relative_path=source_rel,
                    work_rel=work_rel,
                    work_path=work_path,
                    capability=capability,
                )
                continue
            if kind == "metadata.tags":
                await _run_metadata_tags(
                    plugin_loader=plugin_loader,
                    work_path=work_path,
                    capability=capability,
                )
                continue
            if kind == "publish.write":
                await _run_publish_write(fs=fs, work_rel=work_rel, capability=capability)
                continue
            if kind == "source.delete":
                await _run_source_delete(source_path=source_path, capability=capability)
                continue
            raise ValueError(f"Unsupported capability kind: {kind}")

        emit_required_event(
            "phase2.action.end",
            "phase2.action.end",
            {
                "job_id": job_id,
                "action_index": action_index,
                "book_id": str(action.get("book_id") or ""),
                **diagnostics_context,
            },
        )

    emit_required_event(
        "phase2.runner.end",
        "phase2.runner.end",
        {
            "job_id": job_id,
            "batch_size": len(actions),
            **diagnostics_context,
        },
    )
