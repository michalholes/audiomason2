"""Deterministic metadata projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from functools import lru_cache
from typing import Any

from .metadata_boundary import validate_author_title

DEFAULT_FILENAME_POLICY = {"mode": "keep", "template": "{author}/{title}"}
DEFAULT_FIELD_MAP = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "album_artist": "album_artist",
}
_ROOT_AUDIO_AUTHOR = "__ROOT_AUDIO__"
_ROOT_AUDIO_TITLE = "Untitled"
_ROOT_SENTINELS = {"", "(root)"}
_TRAILING_TAG_RE = re.compile(r"(?:\s*(?:\([^)]*\)|\[[^]]*\]))+\s*$")
_DURATION_SUFFIX_RE = re.compile(r"\s*\(\d+h\d+m(?:\d+s)?\)\s*$", re.IGNORECASE)


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _cleanup_whitespace(text: str) -> str:
    return " ".join(part for part in str(text).replace("_", " ").split() if part)


def _strip_trailing_tags(text: str) -> str:
    previous = str(text)
    while True:
        updated = _TRAILING_TAG_RE.sub("", previous).strip()
        if updated == previous:
            return updated
        previous = updated


def _normalize_source_author_label(value: Any) -> str:
    text = _cleanup_whitespace(str(value or ""))
    text = _strip_trailing_tags(text)
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            text = f"{parts[1]} {parts[0]}"
    text = _cleanup_whitespace(_ascii_fold(text))
    return text


def _normalize_source_title_label(*, author: str, value: Any) -> str:
    raw = _cleanup_whitespace(str(value or ""))
    raw = _DURATION_SUFFIX_RE.sub("", raw).strip()
    raw = _strip_trailing_tags(raw)
    folded = _cleanup_whitespace(_ascii_fold(raw))
    folded_author = _cleanup_whitespace(_ascii_fold(author))
    if folded_author:
        lower_author = folded_author.lower()
        if folded.lower().startswith(lower_author + " - "):
            folded = folded[len(folded_author) + 3 :].strip()
        elif folded.lower().startswith(lower_author + "/"):
            folded = folded[len(folded_author) + 1 :].strip()
    return _cleanup_whitespace(folded)


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _normalize_root_audio_value(*, value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if text in _ROOT_SENTINELS:
        return fallback
    return text or fallback


@lru_cache(maxsize=128)
def _openlibrary_validate(author: str, title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return validate_author_title(author, title)


def _validated_author_title(*, author: str, title: str) -> tuple[dict[str, Any], str, str]:
    author_validation, book_validation = _openlibrary_validate(author, title)

    canonical_author = str(author_validation.get("canonical") or author)
    suggestion_author = author_validation.get("suggestion")
    if isinstance(suggestion_author, str) and suggestion_author.strip():
        canonical_author = suggestion_author.strip()

    canonical_title = title
    canonical_book = book_validation.get("canonical")
    suggestion_book = book_validation.get("suggestion")
    if isinstance(canonical_book, dict):
        canonical_author = str(canonical_book.get("author") or canonical_author)
        canonical_title = str(canonical_book.get("title") or canonical_title)
    elif isinstance(suggestion_book, dict):
        canonical_author = str(suggestion_book.get("author") or canonical_author)
        canonical_title = str(suggestion_book.get("title") or canonical_title)

    canonical_author = _normalize_root_audio_value(
        value=canonical_author,
        fallback=_ROOT_AUDIO_AUTHOR,
    )
    canonical_title = _normalize_root_audio_value(
        value=canonical_title,
        fallback=_ROOT_AUDIO_TITLE,
    )

    return (
        {
            "provider": "metadata_openlibrary",
            "author": dict(author_validation),
            "book": dict(book_validation),
        },
        canonical_author,
        canonical_title,
    )


def _sanitize_validation_payload(result_any: Any) -> dict[str, Any] | None:
    if not isinstance(result_any, dict):
        return None
    author_any = result_any.get("author")
    book_any = result_any.get("book")
    return {
        "provider": str(result_any.get("provider") or "metadata_openlibrary"),
        "author": dict(author_any) if isinstance(author_any, dict) else {},
        "book": dict(book_any) if isinstance(book_any, dict) else {},
    }


def _canonicalize_validation_payload(
    *,
    validation: dict[str, Any],
    fallback_author: str,
    fallback_title: str,
) -> tuple[dict[str, Any], str, str]:
    canonical_author = str(fallback_author)
    author_payload = dict(validation.get("author") or {})
    canonical_author_value = author_payload.get("canonical")
    suggestion_author = author_payload.get("suggestion")
    if isinstance(canonical_author_value, str) and canonical_author_value.strip():
        canonical_author = canonical_author_value.strip()
    if isinstance(suggestion_author, str) and suggestion_author.strip():
        canonical_author = suggestion_author.strip()

    canonical_title = str(fallback_title)
    book_payload = dict(validation.get("book") or {})
    canonical_book = book_payload.get("canonical")
    suggestion_book = book_payload.get("suggestion")
    if isinstance(canonical_book, dict):
        canonical_author = str(canonical_book.get("author") or canonical_author)
        canonical_title = str(canonical_book.get("title") or canonical_title)
    elif isinstance(suggestion_book, dict):
        canonical_author = str(suggestion_book.get("author") or canonical_author)
        canonical_title = str(suggestion_book.get("title") or canonical_title)

    canonical_author = _normalize_root_audio_value(
        value=canonical_author,
        fallback=_ROOT_AUDIO_AUTHOR,
    )
    canonical_title = _normalize_root_audio_value(
        value=canonical_title,
        fallback=_ROOT_AUDIO_TITLE,
    )
    return validation, canonical_author, canonical_title


def _explicit_validation_from_state(
    state: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None, bool]:
    for step_id in (
        "metadata_validate_after_title",
        "metadata_validate_after_author",
        "metadata_validate_initial",
    ):
        answer = _answer_dict(state, step_id)
        if answer:
            validation = _sanitize_validation_payload(answer.get("result"))
            return validation, step_id, True
    return None, None, False


def _latest_validation_answer(state: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    for step_id in (
        "metadata_validate_after_title",
        "metadata_validate_after_author",
        "metadata_validate_initial",
    ):
        answer = _answer_dict(state, step_id)
        if answer:
            return answer, step_id
    return {}, None


def _suggested_author(validation: dict[str, Any], fallback: str) -> str:
    author_payload = dict(validation.get("author") or {})
    book_payload = dict(validation.get("book") or {})
    for candidate in (
        author_payload.get("suggestion"),
        author_payload.get("canonical"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return _normalize_source_author_label(candidate)
    for candidate in (
        book_payload.get("suggestion"),
        book_payload.get("canonical"),
    ):
        if isinstance(candidate, dict):
            value = candidate.get("author")
            if isinstance(value, str) and value.strip():
                return _normalize_source_author_label(value)
    return _normalize_source_author_label(fallback)


def _suggested_title(validation: dict[str, Any], fallback_author: str, fallback_title: str) -> str:
    book_payload = dict(validation.get("book") or {})
    for candidate in (
        book_payload.get("canonical"),
        book_payload.get("suggestion"),
    ):
        if isinstance(candidate, dict):
            value = candidate.get("title")
            if isinstance(value, str) and value.strip():
                return _normalize_source_title_label(author=fallback_author, value=value)
    return _normalize_source_title_label(author=fallback_author, value=fallback_title)


def _prompt_examples(*, primary: str, fallback: str) -> list[str]:
    examples: list[str] = []
    for value in (primary, fallback):
        text = str(value or "").strip()
        if text and text not in examples:
            examples.append(text)
    return examples


def _unique_examples(values: list[str], *, fallback: str) -> list[str]:
    examples: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in examples:
            examples.append(text)
    fallback_text = str(fallback or "").strip()
    if fallback_text and fallback_text not in examples:
        examples.append(fallback_text)
    return examples


def _validation_hint(
    *,
    validation: dict[str, Any],
    answer: dict[str, Any],
    normalized_author: str,
    normalized_title: str,
) -> tuple[str, list[str], list[str]]:
    if not answer:
        return (
            "Metadata lookup not available.",
            _prompt_examples(primary=normalized_author, fallback=normalized_author),
            _prompt_examples(primary=normalized_title, fallback=normalized_title),
        )
    error = dict(answer.get("error") or {}) if isinstance(answer.get("error"), dict) else {}
    if error:
        message = str(error.get("message") or error.get("type") or "lookup failed")
        hint = f"Metadata lookup failed: {message}"
        return (
            hint,
            _prompt_examples(primary=normalized_author, fallback=normalized_author),
            _prompt_examples(primary=normalized_title, fallback=normalized_title),
        )

    if not validation:
        return (
            "Metadata lookup found no stronger match.",
            _prompt_examples(primary=normalized_author, fallback=normalized_author),
            _prompt_examples(primary=normalized_title, fallback=normalized_title),
        )

    author_payload = dict(validation.get("author") or {})
    book_payload = dict(validation.get("book") or {})
    author_valid = bool(author_payload.get("valid"))
    book_valid = bool(book_payload.get("valid"))
    has_suggestion = any(
        value is not None
        for value in (
            author_payload.get("suggestion"),
            author_payload.get("canonical"),
            book_payload.get("suggestion"),
            book_payload.get("canonical"),
        )
    )
    suggested_author = _suggested_author(validation, normalized_author)
    suggested_title = _suggested_title(
        validation,
        fallback_author=suggested_author or normalized_author,
        fallback_title=normalized_title,
    )
    if author_valid and book_valid:
        hint = "Metadata lookup found a matching author and title."
    elif has_suggestion:
        hint = "Metadata lookup suggested canonical author/title."
    else:
        hint = "Metadata lookup found no stronger match."
    return (
        hint,
        _prompt_examples(primary=suggested_author, fallback=normalized_author),
        _prompt_examples(primary=suggested_title, fallback=normalized_title),
    )


def build_phase1_metadata_projection(
    *,
    source_projection: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    book_meta_any = source_projection.get("book_meta")
    source_book_meta = dict(book_meta_any) if isinstance(book_meta_any, dict) else {}
    selected_any = source_projection.get("select_books")
    selected = dict(selected_any) if isinstance(selected_any, dict) else {}
    selected_ids_any = selected.get("selected_ids")
    selected_ids = (
        [item for item in selected_ids_any if isinstance(item, str)]
        if isinstance(selected_ids_any, list)
        else []
    )
    selected_paths_any = selected.get("selected_source_relative_paths")
    selected_paths = (
        [item for item in selected_paths_any if isinstance(item, str)]
        if isinstance(selected_paths_any, list)
        else []
    )

    validated_books: dict[str, dict[str, Any]] = {}
    for book_id in selected_ids:
        source_book = source_book_meta.get(book_id, {})
        normalized_source_author = _normalize_source_author_label(source_book.get("author_label"))
        source_author = _normalize_root_audio_value(
            value=normalized_source_author,
            fallback=_ROOT_AUDIO_AUTHOR,
        )
        normalized_source_title = _normalize_source_title_label(
            author=source_author,
            value=source_book.get("book_label"),
        )
        source_title = _normalize_root_audio_value(
            value=normalized_source_title,
            fallback=_ROOT_AUDIO_TITLE,
        )
        validated_books[book_id] = {
            "source_author": source_author,
            "source_title": source_title,
            "author_label": source_author,
            "book_label": source_title,
            "display_label": (
                source_author
                if source_author == source_title
                else f"{source_author} / {source_title}"
            ),
            "source_relative_path": str(source_book.get("source_relative_path") or ""),
            "validation": {},
        }

    first_book = validated_books.get(selected_ids[0], {}) if selected_ids else {}
    source_author = str(first_book.get("source_author") or _ROOT_AUDIO_AUTHOR)
    source_title = str(first_book.get("source_title") or _ROOT_AUDIO_TITLE)

    author_answer = _answer_dict(state, "effective_author")
    title_answer = _answer_dict(state, "effective_title")
    merged_answer = _answer_dict(state, "effective_author_title")

    author_override_raw = author_answer.get("author")
    if author_override_raw is None:
        author_override_raw = merged_answer.get("author")
    title_override_raw = title_answer.get("title")
    if title_override_raw is None:
        title_override_raw = merged_answer.get("title")

    author_override_present = author_override_raw is not None
    title_override_present = title_override_raw is not None
    explicit_validation, explicit_validation_step, explicit_validation_present = (
        _explicit_validation_from_state(state)
    )

    if explicit_validation is not None:
        requested_author = _normalize_root_audio_value(
            value=(author_override_raw if author_override_present else source_author),
            fallback=source_author,
        )
        requested_title = _normalize_root_audio_value(
            value=(title_override_raw if title_override_present else source_title),
            fallback=source_title,
        )
        _, canonical_author, canonical_title = _canonicalize_validation_payload(
            validation=explicit_validation,
            fallback_author=requested_author,
            fallback_title=requested_title,
        )
        apply_title_from_validation = not (
            explicit_validation_step == "metadata_validate_after_author"
            and not title_override_present
        )
        target_ids = selected_ids
        if (
            explicit_validation_step == "metadata_validate_initial"
            and not author_override_present
            and not title_override_present
            and selected_ids
        ):
            target_ids = [selected_ids[0]]
        for book_id in target_ids:
            current = dict(validated_books.get(book_id) or {})
            current_title = str(current.get("book_label") or _ROOT_AUDIO_TITLE)
            applied_title = canonical_title if apply_title_from_validation else current_title
            validated_books[book_id] = {
                **current,
                "author_label": canonical_author,
                "book_label": applied_title,
                "display_label": (
                    canonical_author
                    if canonical_author == applied_title
                    else f"{canonical_author} / {applied_title}"
                ),
                "validation": dict(explicit_validation),
            }
    elif author_override_present or title_override_present:
        for book_id in selected_ids:
            current = dict(validated_books.get(book_id) or {})
            requested_author_source = (
                author_override_raw if author_override_present else current.get("author_label")
            )
            requested_author = _normalize_root_audio_value(
                value=requested_author_source,
                fallback=str(current.get("author_label") or _ROOT_AUDIO_AUTHOR),
            )
            requested_title = _normalize_root_audio_value(
                value=(title_override_raw if title_override_present else current.get("book_label")),
                fallback=str(current.get("book_label") or _ROOT_AUDIO_TITLE),
            )
            validation, canonical_author, canonical_title = _validated_author_title(
                author=requested_author,
                title=requested_title,
            )
            validated_books[book_id] = {
                **current,
                "author_label": canonical_author,
                "book_label": canonical_title,
                "display_label": (
                    canonical_author
                    if canonical_author == canonical_title
                    else f"{canonical_author} / {canonical_title}"
                ),
                "validation": validation,
            }

    effective_book = validated_books.get(selected_ids[0], {}) if selected_ids else {}
    normalized_author = _normalize_root_audio_value(
        value=effective_book.get("author_label"),
        fallback=_ROOT_AUDIO_AUTHOR,
    )
    normalized_book_title = _normalize_root_audio_value(
        value=effective_book.get("book_label"),
        fallback=_ROOT_AUDIO_TITLE,
    )
    effective_author_title = {
        "author": normalized_author,
        "title": normalized_book_title,
    }
    validation = dict(effective_book.get("validation") or {})
    latest_validation_answer, _latest_validation_step = _latest_validation_answer(state)
    (
        author_prompt_hint,
        author_prompt_examples,
        title_prompt_examples,
    ) = _validation_hint(
        validation=validation,
        answer=latest_validation_answer,
        normalized_author=normalized_author,
        normalized_title=normalized_book_title,
    )
    title_prompt_hint = author_prompt_hint
    unique_authors = sorted(
        {
            str(book.get("author_label") or "").strip()
            for book in validated_books.values()
            if isinstance(book, dict) and str(book.get("author_label") or "").strip()
        }
    )
    unique_titles = sorted(
        {
            str(book.get("book_label") or "").strip()
            for book in validated_books.values()
            if isinstance(book, dict) and str(book.get("book_label") or "").strip()
        }
    )
    author_prompt_prefill = normalized_author if len(unique_authors) <= 1 else None
    title_prompt_prefill = normalized_book_title if len(unique_titles) <= 1 else None
    if len(unique_authors) > 1:
        author_prompt_hint = (
            "Multiple selected books have different authors. "
            "Leave blank to keep per-book authors, or enter a common author for all selected books."
        )
        author_prompt_examples = _unique_examples(
            unique_authors[:5],
            fallback=normalized_author,
        )
    if len(unique_titles) > 1:
        title_prompt_hint = (
            "Multiple selected books have different titles. "
            "Leave blank to keep per-book titles, or enter a common title for all selected books."
        )
        title_prompt_examples = _unique_examples(
            unique_titles[:5],
            fallback=normalized_book_title,
        )

    filename_policy = deepcopy(DEFAULT_FILENAME_POLICY)
    filename_policy.update(
        {
            "author": normalized_author,
            "title": normalized_book_title,
        }
    )
    filename_policy.update(_answer_dict(state, "filename_policy"))

    default_values = {
        "title": normalized_book_title,
        "artist": normalized_author,
        "album": normalized_book_title,
        "album_artist": normalized_author,
    }
    id3_policy = {
        "field_map": deepcopy(DEFAULT_FIELD_MAP),
        "values": default_values,
    }
    id3_policy.update(_answer_dict(state, "id3_policy"))
    field_map = dict(id3_policy.get("field_map") or {})
    values = dict(id3_policy.get("values") or {})

    return {
        "source_author": source_author,
        "book_title": source_title,
        "normalize_author": normalized_author,
        "normalize_book_title": normalized_book_title,
        "validation": validation,
        "author_prompt_hint": author_prompt_hint,
        "title_prompt_hint": title_prompt_hint,
        "author_prompt_examples": author_prompt_examples,
        "title_prompt_examples": title_prompt_examples,
        "author_prompt_prefill": author_prompt_prefill,
        "title_prompt_prefill": title_prompt_prefill,
        "effective_author_title": effective_author_title,
        "filename_policy": filename_policy,
        "field_map": field_map,
        "values": values,
        "selected_book_ids": selected_ids,
        "selected_source_relative_paths": selected_paths,
        "authority_by_book": validated_books,
    }
