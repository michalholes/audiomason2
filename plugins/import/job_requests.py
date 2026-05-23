"""PHASE 2 job request generation for import wizard engine.

Job requests are derived from plan.json planned outputs.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard

from plugins.file_io.import_runtime import normalize_relative_path

from .fingerprints import fingerprint_json


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _policy_dict(inputs: dict[str, object], key: str) -> dict[str, object]:
    value = inputs.get(key)
    return dict(value) if _is_str_object_dict(value) else {}


def _tag_values_for_action(
    *,
    inputs: dict[str, object],
    authority_meta: dict[str, object] | None = None,
) -> dict[str, str]:
    authority = dict(authority_meta) if _is_str_object_dict(authority_meta) else {}
    author_name = str(authority.get("author_label") or "")
    book_title = str(authority.get("book_label") or "")
    values = {
        "title": book_title,
        "artist": author_name,
        "album": book_title,
        "album_artist": author_name,
    }
    id3_policy = _policy_dict(inputs, "id3_policy")
    values_any = id3_policy.get("values")
    if _is_str_object_dict(values_any):
        for key, value in values_any.items():
            text_value = str(value or "").strip()
            if text_value:
                values[str(key)] = text_value
    return {key: value for key, value in values.items() if value}


def _string_dict(value: object) -> dict[str, str]:
    if not _is_str_object_dict(value):
        return {}
    out: dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key)
        item_text = str(item) if isinstance(item, str) else ""
        if key_text and item_text:
            out[key_text] = item_text
    return out


def _metadata_field_map(inputs: dict[str, object]) -> dict[str, str]:
    id3_policy = _policy_dict(inputs, "id3_policy")
    return _string_dict(id3_policy.get("field_map"))


def _cover_choice(inputs: dict[str, object], *, book_id: str | None = None) -> dict[str, str]:
    covers_policy = _policy_dict(inputs, "covers_policy")
    if book_id:
        by_book_any = covers_policy.get("by_book")
        by_book = dict(by_book_any) if _is_str_object_dict(by_book_any) else {}
        choice_any = by_book.get(book_id)
        if _is_str_object_dict(choice_any):
            choice = dict(choice_any)
            kind = str(choice.get("kind") or "skip")
            if kind == "url":
                url = str(choice.get("url") or "")
                return {"kind": "url", "url": url} if url else {"kind": "skip"}
            if kind == "candidate":
                return {
                    "kind": "candidate",
                    "candidate_id": str(choice.get("candidate_id") or ""),
                    "source_relative_path": str(choice.get("source_relative_path") or ""),
                }
            return {"kind": "skip"}
    choice_any = covers_policy.get("choice")
    choice = dict(choice_any) if _is_str_object_dict(choice_any) else {}
    kind = str(choice.get("kind") or covers_policy.get("mode") or "skip")
    if kind == "url":
        url = str(choice.get("url") or covers_policy.get("url") or "")
        return {"kind": "url", "url": url} if url else {"kind": "skip"}
    if kind != "candidate":
        return {"kind": "skip"}
    return {
        "kind": "candidate",
        "candidate_id": str(choice.get("candidate_id") or covers_policy.get("candidate_id") or ""),
        "source_relative_path": str(
            choice.get("source_relative_path") or covers_policy.get("source_relative_path") or ""
        ),
    }


def _cover_candidate_for_action(
    *,
    inputs: dict[str, object],
    book_id: str,
    source_relative_path: str,
) -> dict[str, str] | None:
    choice = _cover_choice(inputs, book_id=book_id)
    if choice.get("kind") != "candidate":
        return None
    if choice.get("source_relative_path") != source_relative_path:
        return None

    covers_policy = _policy_dict(inputs, "covers_policy")
    sources_any = covers_policy.get("sources")
    sources = sources_any if _is_object_list(sources_any) else []
    for source in sources:
        if not _is_str_object_dict(source):
            continue
        if str(source.get("source_relative_path") or "") != source_relative_path:
            continue
        candidates_any = source.get("candidates")
        candidates = candidates_any if _is_object_list(candidates_any) else []
        for candidate in candidates:
            if not _is_str_object_dict(candidate):
                continue
            if str(candidate.get("candidate_id") or "") != choice.get("candidate_id"):
                continue
            return {
                key: str(value)
                for key, value in candidate.items()
                if isinstance(key, str) and isinstance(value, str) and value
            }

    candidates_any = covers_policy.get("candidates")
    candidates = candidates_any if _is_object_list(candidates_any) else []
    for candidate in candidates:
        if not _is_str_object_dict(candidate):
            continue
        if str(candidate.get("candidate_id") or "") != choice.get("candidate_id"):
            continue
        if str(candidate.get("source_relative_path") or "") != source_relative_path:
            continue
        return {
            key: str(value)
            for key, value in candidate.items()
            if isinstance(key, str) and isinstance(value, str) and value
        }
    return None


def _rename_authority_for_action(
    *,
    item: dict[str, object],
    book_id: str,
    inputs: dict[str, object],
    rename_by_book: dict[str, object],
) -> dict[str, object]:
    audio_processing = _policy_dict(inputs, "audio_processing")
    if bool(audio_processing.get("split_chapters", False)):
        return {"mode": "keep_generated", "extension": ".mp3"}

    outputs_any = item.get("rename_outputs")
    outputs_raw = outputs_any if _is_object_list(outputs_any) else []
    outputs: list[str] = []
    for value in outputs_raw:
        if not isinstance(value, str):
            continue
        rel_path = normalize_relative_path(value)
        if rel_path and rel_path not in outputs:
            outputs.append(rel_path)
    if outputs:
        return {"mode": "explicit_relative_paths", "outputs": outputs}

    rename_any = rename_by_book.get(book_id)
    rename = dict(rename_any) if _is_str_object_dict(rename_any) else {}
    rename_outputs_any = rename.get("outputs")
    fallback_raw: list[object] = rename_outputs_any if _is_object_list(rename_outputs_any) else []
    for value in fallback_raw:
        if not isinstance(value, str):
            continue
        rel_path = normalize_relative_path(value)
        if rel_path and rel_path not in outputs:
            outputs.append(rel_path)
    if not outputs:
        outputs = ["01.mp3"]
    return {"mode": "explicit_relative_paths", "outputs": outputs}


def _track_start_value(inputs: dict[str, object]) -> int | None:
    id3_policy = _policy_dict(inputs, "id3_policy")
    value = id3_policy.get("track_start")
    try:
        return int(str(value).strip()) if value is not None else None
    except (TypeError, ValueError):
        return None


def _action_authority(
    *,
    book_meta: dict[str, object] | None,
    field_map: dict[str, str],
    tag_values: dict[str, str],
    target_root: str,
    target_relative_path: str,
    track_start: int | None,
    rename_authority: dict[str, object],
) -> dict[str, object]:
    book = dict(book_meta) if _is_str_object_dict(book_meta) else {}
    metadata_tags: dict[str, object] = {
        "field_map": dict(field_map),
        "values": dict(tag_values),
    }
    if track_start is not None:
        metadata_tags["track_start"] = track_start
    return {
        "book": book,
        "metadata_tags": metadata_tags,
        "publish": {
            "root": target_root,
            "relative_path": target_relative_path,
        },
        "rename": dict(rename_authority),
    }


def _build_capabilities(
    *,
    book_id: str,
    root: str,
    source_relative_path: str,
    target_root: str,
    target_relative_path: str,
    inputs: dict[str, object],
    field_map: dict[str, str],
    tag_values: dict[str, str],
    track_start: int | None,
) -> list[dict[str, object]]:
    audio_processing = _policy_dict(inputs, "audio_processing")
    covers_policy = _policy_dict(inputs, "covers_policy")
    conflict_policy = _policy_dict(inputs, "conflict_policy")
    delete_policy = _policy_dict(inputs, "delete_source_policy")

    cover_choice = _cover_choice(inputs, book_id=book_id)
    cover_candidate = _cover_candidate_for_action(
        inputs=inputs,
        book_id=book_id,
        source_relative_path=source_relative_path,
    )
    cover_mode = str(cover_choice.get("kind") or "skip")
    if cover_mode == "candidate":
        cover_mode = str(cover_candidate.get("kind") or "skip") if cover_candidate else "skip"
    conflict_mode = str(conflict_policy.get("mode") or "ask")

    capabilities: list[dict[str, object]] = [
        {
            "kind": "audio.import",
            "order": 10,
            "plugin": "audio_processor",
            "options": {
                "bitrate": str(audio_processing.get("bitrate") or "128k"),
                "loudnorm": bool(audio_processing.get("loudnorm", False)),
                "split_chapters": bool(audio_processing.get("split_chapters", False)),
            },
        }
    ]
    if cover_mode != "skip":
        cover_cap: dict[str, object] = {
            "kind": "cover.embed",
            "order": 20,
            "plugin": "cover_handler",
            "mode": cover_mode,
            "choice": dict(cover_choice),
        }
        if cover_candidate is not None:
            cover_cap["candidate"] = dict(cover_candidate)
        cover_url = str(cover_choice.get("url") or covers_policy.get("url") or "")
        if cover_url:
            cover_cap["url"] = cover_url
        capabilities.append(cover_cap)

    metadata_capability: dict[str, object] = {
        "kind": "metadata.tags",
        "order": 30,
        "plugin": "id3_tagger",
        "field_map": dict(field_map),
        "values": tag_values,
        "wipe_before_write": True,
        "preserve_cover": True,
    }
    if track_start is not None:
        metadata_capability["track_start"] = track_start
    capabilities.append(metadata_capability)
    capabilities.append(
        {
            "kind": "publish.write",
            "order": 40,
            "root": target_root,
            "relative_path": target_relative_path,
            "overwrite": conflict_mode == "overwrite",
        }
    )

    delete_mode = str(delete_policy.get("mode") or "")
    delete_enabled = bool(delete_policy.get("enabled", False)) or delete_mode in {
        "delete",
        "after_publish",
        "always",
    }
    if delete_enabled:
        capabilities.append(
            {
                "kind": "source.delete",
                "order": 50,
                "root": root,
                "relative_path": source_relative_path,
                "enabled": True,
            }
        )
    return capabilities


def build_job_requests(
    *,
    session_id: str,
    root: str,
    relative_path: str,
    mode: str,
    diagnostics_context: dict[str, str],
    config_fingerprint: str,
    plan: dict[str, object],
    inputs: dict[str, object],
    detached_runtime: dict[str, object] | None = None,
    session_authority: dict[str, object] | None = None,
) -> dict[str, object]:
    mode = str(mode)
    if mode not in {"stage", "inplace"}:
        raise ValueError("mode must be 'stage' or 'inplace'")

    selected_any = plan.get("selected_books")
    if not _is_object_list(selected_any):
        selected_any = []

    actions: list[dict[str, object]] = []
    authority = dict(session_authority) if _is_str_object_dict(session_authority) else {}
    phase1_runtime_any = authority.get("runtime")
    phase1_runtime = dict(phase1_runtime_any) if _is_str_object_dict(phase1_runtime_any) else {}
    phase2_inputs_any = authority.get("phase2_inputs")
    phase2_inputs = dict(phase2_inputs_any) if _is_str_object_dict(phase2_inputs_any) else {}
    del inputs
    publish_policy = _policy_dict(phase2_inputs, "publish_policy")
    target_root = str(publish_policy.get("target_root") or "")
    if target_root not in {"stage", "outbox"}:
        target_root = "stage" if mode == "stage" else "outbox"
    book_meta_any = authority.get("authority_book_meta")
    book_meta = dict(book_meta_any) if _is_str_object_dict(book_meta_any) else {}
    field_map = _metadata_field_map(phase2_inputs)
    track_start = _track_start_value(phase2_inputs)
    rename_by_book_any = authority.get("rename_by_book")
    rename_by_book = dict(rename_by_book_any) if _is_str_object_dict(rename_by_book_any) else {}
    selected_book_meta: dict[str, dict[str, object]] = {}
    for it in selected_any:
        if not _is_str_object_dict(it):
            continue
        book_id = it.get("book_id")
        src_rel = it.get("source_relative_path")
        tgt_rel = it.get("proposed_target_relative_path")
        if not isinstance(book_id, str) or not book_id:
            continue
        if not isinstance(src_rel, str) or not isinstance(tgt_rel, str):
            continue
        authority_meta_any = book_meta.get(book_id)
        authority_meta = dict(authority_meta_any) if _is_str_object_dict(authority_meta_any) else {}
        if authority_meta:
            selected_book_meta[book_id] = dict(authority_meta)
        tag_values = _tag_values_for_action(inputs=phase2_inputs, authority_meta=authority_meta)
        rename_authority = _rename_authority_for_action(
            item=it,
            book_id=book_id,
            inputs=phase2_inputs,
            rename_by_book=rename_by_book,
        )
        actions.append(
            {
                "type": "import.book",
                "book_id": book_id,
                "source": {"root": root, "relative_path": src_rel},
                "target": {"root": target_root, "relative_path": tgt_rel},
                "authority": _action_authority(
                    book_meta=authority_meta,
                    field_map=field_map,
                    tag_values=tag_values,
                    target_root=target_root,
                    target_relative_path=tgt_rel,
                    track_start=track_start,
                    rename_authority=rename_authority,
                ),
                "capabilities": _build_capabilities(
                    book_id=book_id,
                    root=root,
                    source_relative_path=src_rel,
                    target_root=target_root,
                    target_relative_path=tgt_rel,
                    inputs=phase2_inputs,
                    field_map=field_map,
                    tag_values=tag_values,
                    track_start=track_start,
                ),
            }
        )

    plan_fingerprint = fingerprint_json({"selected_books": selected_any})

    rename_authority_doc: dict[str, dict[str, object]] = {}
    for action in actions:
        if not _is_str_object_dict(action):
            continue
        book_id = str(action.get("book_id") or "")
        if not book_id:
            continue
        authority = _policy_dict(action, "authority")
        rename_authority_doc[book_id] = _policy_dict(authority, "rename")

    doc: dict[str, object] = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": session_id,
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_summary": plan.get("summary", {}),
        "policies": dict(phase2_inputs),
        "actions": actions,
        "authority": {
            "phase1": {
                "runtime": dict(phase1_runtime),
                "selected_books": selected_book_meta,
                "rename_by_book": rename_authority_doc,
            }
        },
        "diagnostics_context": dict(diagnostics_context),
        "plan_fingerprint": plan_fingerprint,
        "detached_runtime": (
            dict(detached_runtime) if _is_str_object_dict(detached_runtime) else {}
        ),
    }

    idem_payload = {
        "mode": mode,
        "config_fingerprint": config_fingerprint,
        "plan_fingerprint": plan_fingerprint,
        "policies_fingerprint": fingerprint_json(phase2_inputs),
    }
    doc["idempotency_key"] = fingerprint_json(idem_payload)
    return doc


def planned_units_count(plan: dict[str, object]) -> int:
    selected_any = plan.get("selected_books")
    if not _is_object_list(selected_any):
        return 0
    return len([it for it in selected_any if _is_str_object_dict(it)])
