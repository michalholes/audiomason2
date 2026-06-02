"""AI-backed title validation provider for Import Phase 1.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import json
import re
from functools import partial
from http.client import HTTPResponse
from typing import TypeGuard, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from audiomason.core.errors import MetadataError
from audiomason.core.serde import json_loads_object


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _to_non_empty_str_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _to_bool_or_default(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in {"1", "true", "yes", "on"}:
            return True
        if norm in {"0", "false", "no", "off"}:
            return False
    return default


def _to_float_or_default(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _safe_error_message(exc: Exception) -> str:
    text = str(exc).strip()
    return text if text else exc.__class__.__name__


def _strip_code_fence(text: str) -> str:
    content = text.strip()
    if not content.startswith("```"):
        return content
    content = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", content)
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _read_response_bytes(
    *,
    req: Request,
    payload: bytes,
    timeout_seconds: float,
    max_response_bytes: int,
) -> bytes:
    chunk_size = 64 * 1024
    with cast(
        HTTPResponse,
        urlopen(req, data=payload, timeout=timeout_seconds),
    ) as response:  # noqa: S310
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_response_bytes:
                raise MetadataError("API request failed: response too large")
            chunks.append(chunk)
    return b"".join(chunks)


class MetadataAIPlugin:
    """AI-backed provider for author/title validation suggestions."""

    REQUEST_VERSION = 1
    JOB_VERSION = 1
    JOB_TYPE = "metadata_ai.request"
    DEFAULT_ENABLED = False
    DEFAULT_ENDPOINT = ""
    DEFAULT_PROVIDER = ""
    DEFAULT_MODEL = ""
    DEFAULT_TIMEOUT_SECONDS = 2.0
    DEFAULT_MAX_RESPONSE_BYTES = 256 * 1024

    def __init__(self, config: dict[str, object] | None = None) -> None:
        self._apply_config(config)

    def _apply_config(self, config: dict[str, object] | None) -> None:
        self.config = dict(config) if config is not None else {}
        self.enabled = _to_bool_or_default(
            self.config.get("enabled"),
            self.DEFAULT_ENABLED,
        )
        self.endpoint = str(
            self.config.get("endpoint") or self.DEFAULT_ENDPOINT,
        ).strip()
        self.provider = str(
            self.config.get("provider") or self.DEFAULT_PROVIDER,
        ).strip()
        self.model = str(
            self.config.get("model") or self.DEFAULT_MODEL,
        ).strip()
        self.api_key = str(self.config.get("api_key") or "").strip()
        self.timeout_seconds = _to_float_or_default(
            self.config.get("timeout_seconds"),
            self.DEFAULT_TIMEOUT_SECONDS,
        )
        self.max_response_bytes = _to_int_or_default(
            self.config.get("max_response_bytes"),
            self.DEFAULT_MAX_RESPONSE_BYTES,
        )

    def configure(self, config: dict[str, object]) -> None:
        self._apply_config(config)

    def build_ai_title_validation_request(self, author: str, title: str) -> dict[str, object]:
        return {
            "request_version": self.REQUEST_VERSION,
            "operation": "ai_title_validate",
            "payload": {
                "author": str(author),
                "title": str(title),
            },
        }

    def build_ai_title_validation_job(self, author: str, title: str) -> dict[str, object]:
        return {
            "job_type": self.JOB_TYPE,
            "job_version": self.JOB_VERSION,
            "provider": "metadata_ai",
            "request": self.build_ai_title_validation_request(author, title),
        }

    async def execute_job(self, job: dict[str, object]) -> dict[str, object]:
        job_type = str(job.get("job_type") or "").strip()
        if job_type != self.JOB_TYPE:
            raise MetadataError(f"Unsupported job type: {job_type}")
        version = _to_int_or_default(job.get("job_version"), self.JOB_VERSION)
        if version != self.JOB_VERSION:
            raise MetadataError(f"Unsupported job version: {version}")
        request = _as_str_object_dict(job.get("request"))
        return await self._execute_request(request)

    async def _execute_request(self, request: dict[str, object]) -> dict[str, object]:
        version = _to_int_or_default(request.get("request_version"), self.REQUEST_VERSION)
        if version != self.REQUEST_VERSION:
            raise MetadataError(f"Unsupported request version: {version}")
        operation = str(request.get("operation") or "").strip()
        payload = _as_str_object_dict(request.get("payload"))
        if operation != "ai_title_validate":
            raise MetadataError(f"Unsupported operation: {operation}")
        return await self._execute_ai_title_validate(
            author=str(payload.get("author") or ""),
            title=str(payload.get("title") or ""),
        )

    async def _execute_ai_title_validate(self, *, author: str, title: str) -> dict[str, object]:
        if not self.enabled:
            return self._neutral_result(author=author, title=title)
        if not author.strip() or not title.strip():
            return self._neutral_result(author=author, title=title)
        if not self.api_key or not self.endpoint or not self.model:
            return self._neutral_result(author=author, title=title)

        try:
            raw_payload = await asyncio.to_thread(
                partial(self._http_post_json, author=author, title=title)
            )
            ai_result = self._extract_ai_result(raw_payload)
            return self._normalize_ai_result(
                author=author,
                title=title,
                ai_result=ai_result,
            )
        except Exception:
            return self._neutral_result(author=author, title=title)

    def _http_post_json(self, *, author: str, title: str) -> dict[str, object]:
        request_payload = self._build_api_payload(author=author, title=title)
        request_bytes = json.dumps(
            request_payload,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        req = Request(
            self.endpoint,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "AudioMason2/metadata_ai",
            },
            method="POST",
        )
        try:
            data = _read_response_bytes(
                req=req,
                payload=request_bytes,
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=self.max_response_bytes,
            )
        except HTTPError as exc:
            raise MetadataError(f"API request failed: HTTP {exc.code}") from exc
        except URLError as exc:
            raise MetadataError(f"API request failed: {_safe_error_message(exc)}") from exc
        except TimeoutError as exc:
            raise MetadataError("API request failed: timeout") from exc
        except MetadataError:
            raise
        except Exception as exc:
            raise MetadataError(f"API request failed: {_safe_error_message(exc)}") from exc

        try:
            parsed = json_loads_object(data.decode("utf-8"))
        except ValueError as exc:
            raise MetadataError(f"Invalid API response: {_safe_error_message(exc)}") from exc
        if not _is_str_object_dict(parsed):
            raise MetadataError("Invalid API response: object expected")
        return parsed

    def _build_api_payload(self, *, author: str, title: str) -> dict[str, object]:
        system_prompt = (
            "You validate audiobook metadata. Return strict JSON only with keys: "
            "is_correct (bool), corrected_author (string or null), "
            "corrected_title (string or null). Never include markdown."
        )
        user_prompt = (
            "Author: "
            + author
            + "\n"
            + "Title: "
            + title
            + "\n"
            + "Check if author and title match a known published book entry."
        )
        return {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

    def _extract_ai_result(self, payload: dict[str, object]) -> dict[str, object]:
        choices_any = payload.get("choices")
        choices = choices_any if _is_object_list(choices_any) else []
        if not choices:
            raise MetadataError("Invalid API response: choices missing")
        first = _as_str_object_dict(choices[0])
        message = _as_str_object_dict(first.get("message"))
        content = _to_non_empty_str_or_none(message.get("content"))
        if content is None:
            raise MetadataError("Invalid API response: content missing")
        raw = _strip_code_fence(content)
        try:
            decoded = json_loads_object(raw)
        except ValueError as exc:
            raise MetadataError(f"Invalid AI JSON content: {_safe_error_message(exc)}") from exc
        if not _is_str_object_dict(decoded):
            raise MetadataError("Invalid AI JSON content: object expected")
        return decoded

    def _normalize_ai_result(
        self,
        *,
        author: str,
        title: str,
        ai_result: dict[str, object],
    ) -> dict[str, object]:
        is_correct = _to_bool_or_default(ai_result.get("is_correct"), False)
        corrected_author = _to_non_empty_str_or_none(ai_result.get("corrected_author"))
        corrected_title = _to_non_empty_str_or_none(ai_result.get("corrected_title"))
        author_changed = corrected_author is not None and corrected_author != author
        title_changed = corrected_title is not None and corrected_title != title

        if is_correct and not author_changed and not title_changed:
            return {
                "provider": "metadata_ai",
                "author": {
                    "valid": False,
                    "canonical": None,
                    "suggestion": None,
                },
                "book": {
                    "valid": True,
                    "canonical": {"author": author, "title": title},
                    "suggestion": None,
                },
            }

        if not author_changed and not title_changed:
            return self._neutral_result(author=author, title=title)

        suggested_author = corrected_author if author_changed else author
        suggested_title = corrected_title if title_changed else title
        if suggested_author is None:
            suggested_author = author
        if suggested_title is None:
            suggested_title = title

        if author_changed or title_changed:
            return {
                "provider": "metadata_ai",
                "author": {
                    "valid": False,
                    "canonical": None,
                    "suggestion": suggested_author if author_changed else None,
                },
                "book": {
                    "valid": False,
                    "canonical": None,
                    "suggestion": {"author": suggested_author, "title": suggested_title},
                },
            }

        return self._neutral_result(author=author, title=title)

    @staticmethod
    def _neutral_result(*, author: str, title: str) -> dict[str, object]:
        _ = author
        _ = title
        return {
            "provider": "metadata_ai",
            "author": {
                "valid": False,
                "canonical": None,
                "suggestion": None,
            },
            "book": {
                "valid": False,
                "canonical": None,
                "suggestion": None,
            },
        }


__all__ = ["MetadataAIPlugin"]
