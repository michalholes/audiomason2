"""Deterministic PHASE 0/1 source intake projection for import sessions.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TypeGuard, cast

from plugins.file_io.service import ArchiveService, FileService, RootName

from .fingerprints import sha256_hex
from .phase1_cover_flow import build_phase1_cover_projection
from .phase1_metadata_flow import build_phase1_metadata_projection
from .phase1_policy_flow import build_phase1_policy_projection


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


_PHASE1_AUDIO_SUFFIXES = {".m4a", ".m4b", ".mp3", ".opus"}
_ARCHIVE_SUFFIXES = (
    ".tar.bz2",
    ".tar.gz",
    ".tar",
    ".tgz",
    ".zip",
    ".rar",
    ".7z",
)


def _is_audio_rel_path(rel: str) -> bool:
    rel_lower = rel.lower()
    return any(rel_lower.endswith(suffix) for suffix in _PHASE1_AUDIO_SUFFIXES)


def _looks_like_archive_label(label: str) -> bool:
    lower = label.lower()
    return any(lower.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _archive_segment_match(*, rel_path: str, archive_label: str) -> bool:
    if rel_path.startswith(archive_label + "/"):
        return True
    return f"/{archive_label}/" in rel_path


def _item_sort_key(item: dict[str, str]) -> tuple[str, str]:
    return (item.get("label", ""), item.get("item_id", ""))


def _answer_dict(state: dict[str, object], key: str) -> dict[str, object]:
    answers = _as_str_object_dict(state.get("answers"))
    value = answers.get(key)
    return _as_str_object_dict(value)


def _canonical_selected_author_labels(
    *,
    source_projection: dict[str, object],
    authority_by_book: dict[str, object],
) -> list[str]:
    select_authors = _as_str_object_dict(source_projection.get("select_authors"))
    selected_author_ids = _as_str_list(select_authors.get("selected_ids"))
    existing_labels = _as_str_list(select_authors.get("selected_author_label_list"))
    author_to_books = _as_str_object_dict(source_projection.get("author_to_books"))

    normalized_labels: list[str] = []
    for index, author_id in enumerate(selected_author_ids):
        fallback = existing_labels[index] if index < len(existing_labels) else ""
        candidate = ""
        for book_id in _as_str_list(author_to_books.get(author_id)):
            authority_book = _as_str_object_dict(authority_by_book.get(book_id))
            value = str(authority_book.get("author_label") or "").strip()
            if value:
                candidate = value
                break
        normalized_labels.append(candidate or fallback)
    return normalized_labels


def _canonical_selected_book_labels(
    *,
    source_projection: dict[str, object],
    authority_by_book: dict[str, object],
) -> list[str]:
    select_books = _as_str_object_dict(source_projection.get("select_books"))
    selected_book_ids = _as_str_list(select_books.get("selected_ids"))
    existing_labels = _as_str_list(select_books.get("selected_book_label_list"))

    normalized_labels: list[str] = []
    for index, book_id in enumerate(selected_book_ids):
        fallback = existing_labels[index] if index < len(existing_labels) else ""
        authority_book = _as_str_object_dict(authority_by_book.get(book_id))
        candidate = str(authority_book.get("book_label") or "").strip()
        normalized_labels.append(candidate or fallback)
    return normalized_labels


def _build_runtime_projection(
    *,
    state: dict[str, object],
    metadata_projection: dict[str, object],
    cover_projection: dict[str, object],
    policy_projection: dict[str, object],
    phase2_inputs: dict[str, object],
) -> dict[str, object]:
    conflicts = _as_str_object_dict(state.get("conflicts"))
    has_conflicts = bool(conflicts.get("present")) or bool(conflicts.get("items"))
    conflict_policy = _as_str_object_dict(phase2_inputs.get("conflict_policy"))
    conflict_mode = str(conflict_policy.get("mode") or "ask")

    final_summary_confirm: dict[str, object] = {"confirm_start": False}
    final_summary_confirm.update(_answer_dict(state, "final_summary_confirm"))

    computed = _as_str_object_dict(state.get("computed"))
    summary_any = computed.get("plan_summary")
    summary = _as_str_object_dict(summary_any)

    selected_paths_any = cover_projection.get("selected_source_relative_paths")
    selected_paths = _as_str_list(selected_paths_any)

    return {
        "plan_preview_batch": {
            "summary": deepcopy(summary),
            "selected_source_relative_paths": deepcopy(selected_paths),
            "has_conflicts": has_conflicts,
        },
        "effective_author_title": deepcopy(
            _as_str_object_dict(metadata_projection.get("effective_author_title"))
        ),
        "filename_policy": deepcopy(
            _as_str_object_dict(metadata_projection.get("filename_policy"))
        ),
        "covers_policy": deepcopy(_as_str_object_dict(phase2_inputs.get("covers_policy"))),
        "skip_processed_books": deepcopy(
            _as_str_object_dict(phase2_inputs.get("skip_processed_books"))
        ),
        "id3_policy": deepcopy(_as_str_object_dict(phase2_inputs.get("id3_policy"))),
        "audio_processing": deepcopy(_as_str_object_dict(phase2_inputs.get("audio_processing"))),
        "publish_policy": deepcopy(_as_str_object_dict(phase2_inputs.get("publish_policy"))),
        "delete_source_policy": deepcopy(
            _as_str_object_dict(phase2_inputs.get("delete_source_policy"))
        ),
        "conflict_policy": deepcopy(conflict_policy),
        "parallelism": deepcopy(_as_str_object_dict(policy_projection.get("parallelism"))),
        "final_summary_confirm": final_summary_confirm,
        "resolve_conflicts_batch": {
            "confirm": False,
            "has_conflicts": has_conflicts,
            "required": conflict_mode == "ask" and has_conflicts,
            "policy": conflict_mode,
        },
        "phase2_inputs": deepcopy(phase2_inputs),
        "metadata": deepcopy(metadata_projection),
        "cover": deepcopy(cover_projection),
        "policy": deepcopy(policy_projection),
    }


def _selection_expr(*, ordered_ids: list[str], selected_ids: list[str]) -> str:
    if not ordered_ids:
        return ""
    if len(ordered_ids) == 1 and selected_ids == ordered_ids:
        return "1"
    if selected_ids == ordered_ids:
        return "all"
    index_map = {item_id: index for index, item_id in enumerate(ordered_ids, start=1)}
    indices = [index_map[item_id] for item_id in ordered_ids if item_id in set(selected_ids)]
    return ",".join(str(index) for index in indices)


def _normalize_rel_path(value: str) -> str:
    rel = value.replace("\\", "/").strip("/")
    return "/".join(part for part in rel.split("/") if part)


def _strip_source_prefix(*, rel_path: str, source_prefix: str) -> str:
    if not source_prefix:
        return rel_path
    if rel_path == source_prefix:
        return ""
    prefix = source_prefix + "/"
    if rel_path.startswith(prefix):
        return rel_path[len(prefix) :]
    return rel_path


def _scope_tail(scope_path: str) -> str:
    parts = [part for part in scope_path.split("/") if part]
    return parts[-1] if parts else "(root)"


def _scope_parent_tail(scope_path: str) -> str:
    parts = [part for part in scope_path.split("/") if part]
    return parts[-2] if len(parts) >= 2 else _scope_tail(scope_path)


def _collect_scoped_entries(
    *,
    discovery: list[dict[str, object]],
    state: dict[str, object],
) -> tuple[str, list[str], list[str], list[tuple[str, str]]]:
    source_any = state.get("source")
    source = dict(source_any) if _is_str_object_dict(source_any) else {}
    source_prefix = _normalize_rel_path(str(source.get("relative_path") or ""))

    dirs_all: list[str] = []
    audio_files: list[str] = []
    bundle_files: list[tuple[str, str]] = []

    def _is_nonempty_file(size: object) -> bool:
        if isinstance(size, bool):
            return False
        if isinstance(size, int):
            return size > 0
        return True

    def _is_ancestor_dir(*, dir_rel: str, file_rel: str) -> bool:
        if not dir_rel:
            return True
        return file_rel == dir_rel or file_rel.startswith(dir_rel + "/")

    for item in discovery:
        if not _is_str_object_dict(item):
            continue
        rel_any = item.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel_full = _normalize_rel_path(rel_any)
        rel = _strip_source_prefix(rel_path=rel_full, source_prefix=source_prefix)
        kind = str(item.get("kind") or "")
        if kind == "dir":
            dirs_all.append(rel)
        elif kind in {"file", "bundle"}:
            if not _is_nonempty_file(item.get("size")):
                continue
            if kind == "bundle":
                bundle_files.append((rel, rel_full))
            elif _is_audio_rel_path(rel):
                audio_files.append(rel)

    content_files = [*audio_files, *[scoped for scoped, _ in bundle_files]]

    dirs = [
        rel
        for rel in dirs_all
        if any(_is_ancestor_dir(dir_rel=rel, file_rel=file_rel) for file_rel in content_files)
    ]
    return source_prefix, dirs, audio_files, bundle_files


def _source_root_name(state: dict[str, object]) -> RootName | None:
    source = _as_str_object_dict(state.get("source"))
    root_text = str(source.get("root") or "")
    if not root_text:
        return None
    try:
        return RootName(root_text)
    except ValueError:
        return None


def _archive_stem(label: str) -> str:
    lower = label.lower()
    for suffix in sorted(_ARCHIVE_SUFFIXES, key=len, reverse=True):
        if lower.endswith(suffix):
            return label[: -len(suffix)]
    return label


def _archive_parent_scope_parts(*, entry: str, bundle_label: str) -> list[str]:
    parts = [part for part in entry.split("/") if part]
    parent_parts = parts[:-1]
    stem = _archive_stem(bundle_label).strip().lower()
    if stem and len(parent_parts) >= 2 and parent_parts[0].strip().lower() == stem:
        return parent_parts[1:]
    return parent_parts


def _archive_pair_labels(
    *,
    bundle_label: str,
    parent_parts: list[str],
    entry_audio_stem: str,
    bundle_author_hint: str,
) -> tuple[str, str, list[str]]:
    if len(parent_parts) >= 2:
        author_key = parent_parts[0]
        book_key = parent_parts[1]
        return author_key, book_key, [author_key, book_key]
    if len(parent_parts) == 1:
        label = parent_parts[0]
        author_key = bundle_author_hint.strip() or _author_hint_from_label(label).strip() or label
        return author_key, label, [label]
    stem = _archive_stem(bundle_label).strip()
    book_key = entry_audio_stem.strip() or stem or bundle_label
    author_key = bundle_author_hint.strip() or _author_hint_from_label(book_key).strip() or book_key
    return author_key, book_key, []


def _audio_entry_stem(entry: str) -> str:
    parts = [part for part in entry.split("/") if part]
    if not parts:
        return ""
    filename = parts[-1]
    lower = filename.lower()
    for suffix in sorted(_PHASE1_AUDIO_SUFFIXES, key=len, reverse=True):
        if lower.endswith(suffix):
            return filename[: -len(suffix)]
    name, _sep, _suffix = filename.rpartition(".")
    return name or filename


def _author_hint_from_label(label: str) -> str:
    text = " ".join(part for part in str(label).replace("_", " ").split() if part)
    if not text:
        return ""
    if " - " in text:
        left = text.split(" - ", 1)[0].strip()
        if left:
            return left
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return f"{parts[1]} {parts[0]}".strip()
    return ""


def _label_key(label: str) -> str:
    normalized = " ".join(part for part in str(label).replace("_", " ").split() if part)
    return normalized.lower()


def _bundle_author_hint(*, bundle_label: str, entries: list[str]) -> str:
    scores: dict[str, int] = {}
    labels: dict[str, str] = {}
    for entry in sorted(entries):
        if not _is_audio_rel_path(entry):
            continue
        parent_parts = _archive_parent_scope_parts(entry=entry, bundle_label=bundle_label)
        entry_audio_stem = _audio_entry_stem(entry)

        hint = ""
        if len(parent_parts) >= 2:
            hint = parent_parts[0].strip()
        elif len(parent_parts) == 1:
            hint = _author_hint_from_label(parent_parts[0]).strip()
        else:
            hint = _author_hint_from_label(entry_audio_stem).strip()

        if not hint:
            continue
        key = _label_key(hint)
        if not key:
            continue
        scores[key] = scores.get(key, 0) + 1
        labels.setdefault(key, hint)

    if not scores:
        return ""

    def _score_key(candidate: str) -> tuple[int, str, str]:
        return (-scores[candidate], labels.get(candidate, ""), candidate)

    ranked_keys = sorted(scores, key=_score_key)
    best_key = ranked_keys[0]
    return labels.get(best_key, "")


def _archive_pairs_for_bundle(
    *,
    bundle_rel: str,
    bundle_label: str,
    entries: list[str],
) -> set[tuple[str, str, str]]:
    pairs: set[tuple[str, str, str]] = set()
    bundle_author_hint = _bundle_author_hint(bundle_label=bundle_label, entries=entries)
    for entry in sorted(entries):
        if not _is_audio_rel_path(entry):
            continue
        parent_parts = _archive_parent_scope_parts(entry=entry, bundle_label=bundle_label)
        entry_audio_stem = _audio_entry_stem(entry)
        author_key, book_key, scope_parts = _archive_pair_labels(
            bundle_label=bundle_label,
            parent_parts=parent_parts,
            entry_audio_stem=entry_audio_stem,
            bundle_author_hint=bundle_author_hint,
        )
        source_rel = bundle_rel
        if scope_parts:
            source_rel = _normalize_rel_path(f"{bundle_rel}/{'/'.join(scope_parts)}")
        else:
            source_rel = _normalize_rel_path(f"{bundle_rel}/{entry}")
        pairs.add(
            (
                author_key,
                book_key,
                source_rel,
            )
        )
    return pairs


def _bundle_pairs_from_archive(
    *,
    bundle_rel: str,
    bundle_full_rel: str,
    bundle_label: str,
    state: dict[str, object],
    fs: object | None,
) -> set[tuple[str, str, str]]:
    if not isinstance(fs, FileService):
        return set()
    if not _looks_like_archive_label(bundle_label):
        return set()
    source_root = _source_root_name(state)
    if source_root is None:
        return set()
    archive_service = ArchiveService(fs)
    try:
        plan = archive_service.plan_unpack(
            source_root,
            bundle_full_rel,
            RootName.STAGE,
            "import/phase1_archive_probe",
            autodetect=True,
            preserve_tree=True,
            flatten=False,
        )
    except Exception:
        return set()
    entries = [_normalize_rel_path(entry) for entry in plan.entries]
    return _archive_pairs_for_bundle(
        bundle_rel=bundle_rel,
        bundle_label=bundle_label,
        entries=entries,
    )


def _pairs_for_bundle_files(
    *,
    bundle_files: list[tuple[str, str]],
    state: dict[str, object],
    fs: object | None,
) -> set[tuple[str, str, str]]:
    pairs: set[tuple[str, str, str]] = set()
    for rel, full_rel in bundle_files:
        parts = [part for part in rel.split("/") if part]
        if not parts:
            continue
        bundle_name = parts[-1]
        archive_pairs = _bundle_pairs_from_archive(
            bundle_rel=rel,
            bundle_full_rel=full_rel,
            bundle_label=bundle_name,
            state=state,
            fs=fs,
        )
        if archive_pairs:
            pairs.update(archive_pairs)
            continue
        fallback_label = _archive_stem(bundle_name).strip() or bundle_name
        author_key = parts[0] if len(parts) >= 2 else fallback_label
        pairs.add((author_key, fallback_label, rel))
    return pairs


def _scoped_depth(*, rel_path: str, is_file: bool) -> int:
    parts = [part for part in rel_path.split("/") if part]
    if is_file and parts:
        return len(parts[:-1])
    return len(parts)


def _scope_kind(*, source_prefix: str, dirs: list[str], files: list[str]) -> str:
    if not source_prefix:
        return "root"
    depths = [_scoped_depth(rel_path=rel, is_file=False) for rel in dirs if rel]
    depths.extend(_scoped_depth(rel_path=rel, is_file=True) for rel in files if rel)
    max_depth = max(depths, default=0)
    if max_depth >= 2:
        return "container"
    if max_depth == 1:
        return "author"
    if len([part for part in source_prefix.split("/") if part]) >= 2:
        return "book"
    return "container"


def _pairs_for_multilevel_scope(
    *,
    dirs: list[str],
    files: list[str],
) -> set[tuple[str, str, str]]:
    pairs: set[tuple[str, str, str]] = set()
    for rel in dirs:
        parts = [part for part in rel.split("/") if part]
        if len(parts) >= 2:
            pairs.add((parts[0], parts[1], f"{parts[0]}/{parts[1]}"))
    if not pairs:
        for rel in dirs:
            parts = [part for part in rel.split("/") if part]
            if parts:
                pairs.add((parts[0], parts[0], parts[0]))
    if not pairs:
        for rel in files:
            parts = [part for part in rel.split("/") if part]
            parent_parts = parts[:-1]
            if len(parent_parts) >= 2:
                pairs.add(
                    (
                        parent_parts[0],
                        parent_parts[1],
                        f"{parent_parts[0]}/{parent_parts[1]}",
                    )
                )
            elif len(parent_parts) == 1:
                pairs.add((parent_parts[0], parent_parts[0], parent_parts[0]))
            elif parts:
                pairs.add(("(root)", "(root)", ""))
    return pairs


def _pairs_for_author_scope(
    *,
    source_prefix: str,
    dirs: list[str],
    files: list[str],
) -> set[tuple[str, str, str]]:
    author_key = _scope_tail(source_prefix)
    pairs: set[tuple[str, str, str]] = set()
    for rel in dirs:
        parts = [part for part in rel.split("/") if part]
        if parts:
            pairs.add((author_key, parts[0], parts[0]))
    if not pairs:
        for rel in files:
            parent_parts = [part for part in rel.split("/") if part][:-1]
            if parent_parts:
                pairs.add((author_key, parent_parts[0], parent_parts[0]))
    if not pairs:
        pairs.add((author_key, author_key, ""))
    return pairs


def _pairs_for_book_scope(source_prefix: str) -> set[tuple[str, str, str]]:
    author_key = _scope_parent_tail(source_prefix)
    book_key = _scope_tail(source_prefix)
    return {(author_key, book_key, "")}


def _discovery_pairs(
    *,
    discovery: list[dict[str, object]],
    state: dict[str, object],
    fs: object | None = None,
) -> tuple[list[tuple[str, str, str]], str]:
    source_prefix, dirs, files, bundle_files = _collect_scoped_entries(
        discovery=discovery,
        state=state,
    )
    scope_kind = _scope_kind(source_prefix=source_prefix, dirs=dirs, files=files)
    if not dirs and not files and not bundle_files:
        return [], scope_kind
    if scope_kind in {"root", "container"}:
        pairs = _pairs_for_multilevel_scope(dirs=dirs, files=files)
    elif scope_kind == "author":
        pairs = _pairs_for_author_scope(
            source_prefix=source_prefix,
            dirs=dirs,
            files=files,
        )
    else:
        pairs = _pairs_for_book_scope(source_prefix)

    pairs.update(
        _pairs_for_bundle_files(
            bundle_files=bundle_files,
            state=state,
            fs=fs,
        )
    )
    return sorted(pairs), scope_kind


def _book_pairs(
    *,
    discovery: list[dict[str, object]],
    state: dict[str, object],
    fs: object | None = None,
) -> tuple[
    dict[str, list[str]],
    dict[str, dict[str, str]],
    list[str],
    list[str],
    str,
]:
    pairs, scope_kind = _discovery_pairs(discovery=discovery, state=state, fs=fs)

    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}
    author_to_books: dict[str, list[str]] = {}
    book_meta: dict[str, dict[str, str]] = {}

    for author_key, book_key, source_relative_path in pairs:
        display_label = author_key if author_key == book_key else f"{author_key} / {book_key}"
        if _looks_like_archive_label(author_key) and _archive_segment_match(
            rel_path=source_relative_path,
            archive_label=author_key,
        ):
            display_label = book_key
        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]
        authors.setdefault(author_id, {"item_id": author_id, "label": author_key})
        books.setdefault(book_id, {"item_id": book_id, "label": display_label})
        author_to_books.setdefault(author_id, []).append(book_id)
        book_meta[book_id] = {
            "author_label": author_key,
            "book_label": book_key,
            "display_label": display_label,
            "source_relative_path": source_relative_path,
        }

    author_items = sorted(authors.values(), key=_item_sort_key)
    book_items = sorted(books.values(), key=_item_sort_key)
    author_ids = [item["item_id"] for item in author_items]
    book_ids = [item["item_id"] for item in book_items]

    for author_id in author_to_books:
        seen: set[str] = set()
        ordered: list[str] = []
        for book_id in book_ids:
            if book_id in author_to_books[author_id] and book_id not in seen:
                ordered.append(book_id)
                seen.add(book_id)
        author_to_books[author_id] = ordered

    return author_to_books, book_meta, author_ids, book_ids, scope_kind


def build_phase1_source_projection(
    *,
    discovery: list[dict[str, object]],
    state: dict[str, object],
    fs: object | None = None,
) -> dict[str, object]:
    author_to_books, book_meta, author_ids, book_ids, scope_kind = _book_pairs(
        discovery=discovery,
        state=state,
        fs=fs,
    )

    allow_autofill = scope_kind in {"root", "author", "book"}

    selected_author_ids_any = state.get("selected_author_ids")
    selected_author_ids = (
        [
            item_id
            for item_id in selected_author_ids_any
            if isinstance(item_id, str) and item_id in set(author_ids)
        ]
        if _is_object_list(selected_author_ids_any)
        else []
    )
    if not selected_author_ids:
        selected_author_ids = list(author_ids) if len(author_ids) != 1 else [author_ids[0]]

    filtered_book_ids: list[str] = []
    for author_id in selected_author_ids:
        filtered_book_ids.extend(author_to_books.get(author_id, []))
    if not filtered_book_ids:
        filtered_book_ids = list(book_ids)
    filtered_book_ids = [book_id for book_id in book_ids if book_id in set(filtered_book_ids)]

    selected_book_ids_any = state.get("selected_book_ids")
    selected_book_ids = (
        [
            item_id
            for item_id in selected_book_ids_any
            if isinstance(item_id, str) and item_id in set(filtered_book_ids)
        ]
        if _is_object_list(selected_book_ids_any)
        else []
    )
    if not selected_book_ids:
        selected_book_ids = (
            list(filtered_book_ids) if len(filtered_book_ids) != 1 else [filtered_book_ids[0]]
        )

    return {
        "author_to_books": author_to_books,
        "book_meta": book_meta,
        "select_authors": {
            "ordered_ids": author_ids,
            "selection_expr": _selection_expr(
                ordered_ids=author_ids,
                selected_ids=selected_author_ids,
            ),
            "autofill_if": allow_autofill and len(author_ids) == 1,
            "selected_ids": selected_author_ids,
            "author_label_list": [
                book_meta[author_to_books[aid][0]]["author_label"]
                for aid in author_ids
                if author_to_books.get(aid)
            ],
            "selected_author_label_list": [
                book_meta[author_to_books[aid][0]]["author_label"]
                if author_to_books.get(aid)
                else ""
                for aid in selected_author_ids
            ],
        },
        "select_books": {
            "ordered_ids": book_ids,
            "filtered_ids": filtered_book_ids,
            "selection_expr": _selection_expr(
                ordered_ids=filtered_book_ids,
                selected_ids=selected_book_ids,
            ),
            "autofill_if": allow_autofill and len(filtered_book_ids) == 1,
            "selected_ids": selected_book_ids,
            "selected_source_relative_paths": [
                book_meta.get(book_id, {}).get("source_relative_path", "")
                for book_id in selected_book_ids
                if isinstance(book_meta.get(book_id), dict)
            ],
            "selected_book_label_list": [
                book_meta.get(book_id, {}).get("book_label", "")
                for book_id in selected_book_ids
                if isinstance(book_meta.get(book_id), dict)
            ],
        },
    }


def phase1_session_authority_applies(*, effective_model: dict[str, object]) -> bool:
    steps_any = effective_model.get("steps")
    if not _is_object_list(steps_any):
        return False
    step_ids = {
        str(step.get("step_id") or "")
        for step in steps_any
        if _is_str_object_dict(step) and isinstance(step.get("step_id"), str)
    }
    return {"select_authors", "select_books"}.issubset(step_ids)


def build_phase1_projection(
    *,
    discovery: list[dict[str, object]],
    state: dict[str, object],
    fs: object | None = None,
) -> dict[str, object]:
    source_projection = build_phase1_source_projection(
        discovery=discovery,
        state=state,
        fs=fs,
    )
    metadata_projection = build_phase1_metadata_projection(
        source_projection=source_projection,
        state=state,
    )
    cover_projection = build_phase1_cover_projection(
        discovery=discovery,
        source_projection=source_projection,
        state=state,
        fs=cast(FileService | None, fs),
    )
    policy_projection = build_phase1_policy_projection(
        state=state,
        source_projection=source_projection,
    )
    authority_by_book_any = metadata_projection.get("authority_by_book")
    authority_by_book = _as_str_object_dict(authority_by_book_any)
    select_books = _as_str_object_dict(source_projection.get("select_books"))
    selected_ids = _as_str_list(select_books.get("selected_ids"))
    source_book_meta_any = source_projection.get("book_meta")
    source_book_meta = _as_str_object_dict(source_book_meta_any)
    cover_by_source_any = cover_projection.get("by_source_relative_path")
    cover_by_source = _as_str_object_dict(cover_by_source_any)
    covers_by_book: dict[str, dict[str, object]] = {}
    authority_book_meta: dict[str, dict[str, object]] = {}
    for book_id in selected_ids:
        source_book = _as_str_object_dict(source_book_meta.get(book_id))
        authority_book = _as_str_object_dict(authority_by_book.get(book_id))
        authority_book_meta[book_id] = {
            **source_book,
            **authority_book,
        }
        source_relative_path = str(
            source_book.get("source_relative_path")
            or authority_book.get("source_relative_path")
            or ""
        )
        cover_choice_any = cover_by_source.get(source_relative_path)
        default_cover_choice: dict[str, object] = {"kind": "skip"}
        cover_choice = (
            dict(cover_choice_any)
            if _is_str_object_dict(cover_choice_any)
            else default_cover_choice
        )
        covers_by_book[book_id] = cover_choice

    candidates_any = cover_projection.get("candidates")
    candidates = (
        [dict(item) for item in candidates_any if _is_str_object_dict(item)]
        if _is_object_list(candidates_any)
        else []
    )

    sources_any = cover_projection.get("sources")
    sources: list[dict[str, object]] = []
    if _is_object_list(sources_any):
        for item in sources_any:
            if not _is_str_object_dict(item):
                continue
            item_candidates_any = item.get("candidates")
            item_candidates = (
                [
                    dict(candidate)
                    for candidate in item_candidates_any
                    if _is_str_object_dict(candidate)
                ]
                if _is_object_list(item_candidates_any)
                else []
            )
            sources.append(
                {
                    "source_relative_path": str(item.get("source_relative_path") or ""),
                    "candidates": item_candidates,
                }
            )

    phase2_inputs = {
        "covers_policy": {
            "mode": str(cover_projection.get("mode") or "skip"),
            "url": str(cover_projection.get("url") or ""),
            "choice": _as_str_object_dict(cover_projection.get("choice")),
            "by_book": {key: _as_str_object_dict(value) for key, value in covers_by_book.items()},
            "by_source_relative_path": {
                key: _as_str_object_dict(value) for key, value in cover_by_source.items()
            },
            "candidates": candidates,
            "sources": sources,
            "selected_source_relative_paths": _as_str_list(
                cover_projection.get("selected_source_relative_paths")
            ),
            "has_single_candidate": bool(cover_projection.get("has_single_candidate", False)),
        },
        "id3_policy": {
            "field_map": _as_str_object_dict(metadata_projection.get("field_map")),
            "values": _as_str_object_dict(metadata_projection.get("values")),
        },
        "audio_processing": _as_str_object_dict(policy_projection.get("audio_processing")),
        "publish_policy": _as_str_object_dict(policy_projection.get("publish_policy")),
        "delete_source_policy": _as_str_object_dict(policy_projection.get("delete_source_policy")),
        "skip_processed_books": _as_str_object_dict(
            policy_projection.get("skip_processed_books_policy")
        ),
        "conflict_policy": _as_str_object_dict(policy_projection.get("conflict_policy")),
    }
    conflicts = _as_str_object_dict(state.get("conflicts"))
    phase1_projection = {
        **source_projection,
        "metadata": metadata_projection,
        "cover": cover_projection,
        "policy": policy_projection,
        "conflicts_present": bool(conflicts.get("present")) or bool(conflicts.get("items")),
        "effective_author_title": _as_str_object_dict(
            metadata_projection.get("effective_author_title")
        ),
        "filename_policy": _as_str_object_dict(metadata_projection.get("filename_policy")),
        "parallelism": _as_str_object_dict(policy_projection.get("parallelism")),
        "authority_book_meta": authority_book_meta,
        "normalized_author": str(metadata_projection.get("normalize_author") or ""),
        "normalized_book_title": str(metadata_projection.get("normalize_book_title") or ""),
        "clean_inbox": str(policy_projection.get("clean_inbox") or "ask"),
        "skip_processed_books": bool(policy_projection.get("skip_processed_books", True)),
        "root_audio_baseline": _as_str_object_dict(policy_projection.get("root_audio_baseline")),
        "two_pass_order": _as_str_list(policy_projection.get("two_pass_order")),
        "phase2_inputs": phase2_inputs,
    }
    phase2_inputs_runtime: dict[str, object] = {key: value for key, value in phase2_inputs.items()}
    phase1_projection["runtime"] = _build_runtime_projection(
        state=state,
        metadata_projection=metadata_projection,
        cover_projection=cover_projection,
        policy_projection=policy_projection,
        phase2_inputs=phase2_inputs_runtime,
    )

    select_authors_projection = _as_str_object_dict(phase1_projection.get("select_authors"))
    canonical_labels = _canonical_selected_author_labels(
        source_projection=source_projection,
        authority_by_book=authority_by_book,
    )
    if canonical_labels:
        select_authors_projection["selected_author_label_list"] = canonical_labels
        phase1_projection["select_authors"] = select_authors_projection

    select_books_projection = _as_str_object_dict(phase1_projection.get("select_books"))
    canonical_book_labels = _canonical_selected_book_labels(
        source_projection=source_projection,
        authority_by_book=authority_by_book,
    )
    if canonical_book_labels:
        select_books_projection["selected_book_label_list"] = canonical_book_labels
        phase1_projection["select_books"] = select_books_projection

    return phase1_projection


__all__ = ["build_phase1_projection", "phase1_session_authority_applies"]
