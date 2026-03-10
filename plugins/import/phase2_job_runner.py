"""Plugin-owned PHASE 2 runner for canonical import job requests.

ASCII-only.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from plugins.file_io.import_runtime import normalize_relative_path, publish_staged
from plugins.file_io.service.types import RootName

from .engine_util import _emit_required
from .storage import read_json

_AUDIO_SUFFIXES = {".m4a", ".m4b", ".mp3", ".opus"}
_CHAPTER_SUFFIXES = {".m4a", ".m4b"}


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


def _iter_audio_sources(source_path: Path) -> list[Path]:
    if source_path.is_file():
        return [source_path] if source_path.suffix.lower() in _AUDIO_SUFFIXES else []
    files = [
        path
        for path in sorted(source_path.rglob("*"))
        if path.is_file() and path.suffix.lower() in _AUDIO_SUFFIXES
    ]
    return files


def _iter_mp3_outputs(work_path: Path) -> list[Path]:
    if not work_path.exists():
        return []
    return [path for path in sorted(work_path.rglob("*.mp3")) if path.is_file()]


def _metadata_authority_values(action: dict[str, Any]) -> dict[str, str]:
    authority_any = action.get("authority")
    authority = dict(authority_any) if isinstance(authority_any, dict) else {}
    meta_any = authority.get("metadata_tags")
    meta = dict(meta_any) if isinstance(meta_any, dict) else {}
    values_any = meta.get("values")
    values = dict(values_any) if isinstance(values_any, dict) else {}
    return {
        str(key): str(value)
        for key, value in values.items()
        if str(key) and isinstance(value, str) and value
    }


def _ordered_capabilities(action: dict[str, Any]) -> list[dict[str, Any]]:
    caps_any = action.get("capabilities")
    if not isinstance(caps_any, list):
        return []
    caps = [dict(cap) for cap in caps_any if isinstance(cap, dict)]
    authority_values = _metadata_authority_values(action)
    for cap in caps:
        if str(cap.get("kind") or "") != "metadata.tags":
            continue
        values_any = cap.get("values")
        values = dict(values_any) if isinstance(values_any, dict) else {}
        if values or not authority_values:
            continue
        cap["values"] = dict(authority_values)
    return sorted(caps, key=lambda item: (int(item.get("order") or 0), str(item.get("kind") or "")))


def _resolve_work_relative_path(job_id: str, action_index: int, target_rel: str) -> str:
    suffix = normalize_relative_path(target_rel) or "root"
    return normalize_relative_path(f"import/process_runtime/{job_id}/{action_index:04d}/{suffix}")


def _source_directory(source_path: Path) -> Path:
    return source_path if source_path.is_dir() else source_path.parent


def _first_audio_source(source_path: Path) -> Path | None:
    sources = _iter_audio_sources(source_path)
    return sources[0] if sources else None


async def _run_audio_import(
    *,
    plugin_loader: Any,
    source_path: Path,
    work_path: Path,
    capability: dict[str, Any],
) -> None:
    plugin = plugin_loader.get_plugin("audio_processor")
    options_any = capability.get("options")
    options = dict(options_any) if isinstance(options_any, dict) else {}

    original_values = {
        "bitrate": getattr(plugin, "bitrate", None),
        "loudnorm": getattr(plugin, "loudnorm", None),
        "split_chapters": getattr(plugin, "split_chapters", None),
    }
    if "bitrate" in options:
        plugin.bitrate = str(options["bitrate"])
    if "loudnorm" in options:
        plugin.loudnorm = bool(options["loudnorm"])
    if "split_chapters" in options:
        plugin.split_chapters = bool(options["split_chapters"])

    work_path.mkdir(parents=True, exist_ok=True)
    try:
        for source_file in _iter_audio_sources(source_path):
            relative_parent = (
                source_file.relative_to(source_path).parent if source_path.is_dir() else Path()
            )
            output_dir = work_path / relative_parent
            output_dir.mkdir(parents=True, exist_ok=True)
            chapters: list[dict[str, Any]] | None = None
            if bool(getattr(plugin, "split_chapters", False)) and (
                source_file.suffix.lower() in _CHAPTER_SUFFIXES
            ):
                detect = getattr(plugin, "_detect_chapters", None)
                if callable(detect):
                    chapters = await detect(source_file)
            plan = plugin.plan_import_conversion(source_file, output_dir, chapters=chapters)
            execute_plan = getattr(plugin, "_execute_plan", None)
            if not callable(execute_plan):
                raise RuntimeError("audio_processor missing _execute_plan")
            await execute_plan(plan)
    finally:
        for key, value in original_values.items():
            if value is not None:
                setattr(plugin, key, value)


async def _run_cover_embed(
    *,
    plugin_loader: Any,
    source_path: Path,
    work_path: Path,
    capability: dict[str, Any],
) -> None:
    plugin = plugin_loader.get_plugin("cover_handler")
    mode = str(capability.get("mode") or "skip")
    if mode == "skip":
        return

    cover_path: Path | None = None
    if mode in {"file", "embedded"}:
        directory = _source_directory(source_path)
        audio_file = _first_audio_source(source_path)
        candidates = plugin.discover_cover_candidates(directory, audio_file=audio_file)
        desired_kind = "file" if mode == "file" else "embedded"
        candidate = next(
            (item for item in candidates if str(item.get("kind") or "") == desired_kind),
            None,
        )
        if candidate is not None:
            cover_path = await plugin.apply_cover_candidate(candidate, output_dir=work_path)
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
    plugin_loader: Any,
    work_path: Path,
    capability: dict[str, Any],
) -> None:
    plugin = plugin_loader.get_plugin("id3_tagger")
    values_any = capability.get("values")
    values = dict(values_any) if isinstance(values_any, dict) else {}
    if not values:
        return
    wipe_before_write = bool(capability.get("wipe_before_write", True))
    preserve_cover = bool(capability.get("preserve_cover", True))
    for mp3_file in _iter_mp3_outputs(work_path):
        await plugin.write_tags(
            mp3_file,
            values,
            wipe_before_write=wipe_before_write,
            preserve_cover=preserve_cover,
        )


async def _run_publish_write(
    *,
    fs: Any,
    work_rel: str,
    capability: dict[str, Any],
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


async def _run_source_delete(*, source_path: Path, capability: dict[str, Any]) -> None:
    if bool(capability.get("enabled", False)):
        _remove_path(source_path)


async def run_phase2_job_requests(
    *,
    engine: Any,
    job_id: str,
    job_meta: dict[str, Any],
    plugin_loader: Any,
) -> None:
    fs = engine.get_file_service()
    job_requests_path = str(job_meta.get("job_requests_path") or "")
    if not job_requests_path:
        raise ValueError("job_requests_path is required")

    root, rel_path = _parse_job_requests_path(job_requests_path)
    job_requests_any = read_json(fs, root, rel_path)
    if not isinstance(job_requests_any, dict):
        raise ValueError("job_requests.json is invalid")

    actions_any = job_requests_any.get("actions")
    actions = actions_any if isinstance(actions_any, list) else []
    diagnostics_any = job_requests_any.get("diagnostics_context")
    diagnostics_context = dict(diagnostics_any) if isinstance(diagnostics_any, dict) else {}

    _emit_required(
        "phase2.runner.start",
        "phase2.runner.start",
        {
            "job_id": job_id,
            "batch_size": len(actions),
            **diagnostics_context,
        },
    )

    for action_index, action_any in enumerate(actions, start=1):
        if not isinstance(action_any, dict):
            continue
        action = dict(action_any)
        if str(action.get("type") or "") != "import.book":
            continue
        source_any = action.get("source")
        target_any = action.get("target")
        if not isinstance(source_any, dict) or not isinstance(target_any, dict):
            raise ValueError("action source/target must be objects")
        source_root = RootName(str(source_any.get("root") or ""))
        source_rel = normalize_relative_path(str(source_any.get("relative_path") or ""))
        target_rel = normalize_relative_path(str(target_any.get("relative_path") or ""))
        if not source_rel or not target_rel:
            raise ValueError("action source/target paths must be non-empty")

        source_path = fs.resolve_abs_path(source_root, source_rel)
        work_rel = _resolve_work_relative_path(job_id, action_index, target_rel)
        work_path = fs.resolve_abs_path(RootName.STAGE, work_rel)
        _remove_path(work_path)
        work_path.mkdir(parents=True, exist_ok=True)

        _emit_required(
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
                    plugin_loader=plugin_loader,
                    source_path=source_path,
                    work_path=work_path,
                    capability=capability,
                )
                continue
            if kind == "cover.embed":
                await _run_cover_embed(
                    plugin_loader=plugin_loader,
                    source_path=source_path,
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

        _emit_required(
            "phase2.action.end",
            "phase2.action.end",
            {
                "job_id": job_id,
                "action_index": action_index,
                "book_id": str(action.get("book_id") or ""),
                **diagnostics_context,
            },
        )

    _emit_required(
        "phase2.runner.end",
        "phase2.runner.end",
        {
            "job_id": job_id,
            "batch_size": len(actions),
            **diagnostics_context,
        },
    )
