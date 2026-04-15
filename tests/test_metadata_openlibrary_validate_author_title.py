"""Tests for OpenLibrary author/title validation helpers."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest
from plugins.metadata_openlibrary.plugin import OpenLibraryPlugin


class _FakeOpenLibrary(OpenLibraryPlugin):
    def __init__(
        self,
        docs: list[dict[str, Any]],
        googlebooks_items: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.docs = docs
        self.googlebooks_items = googlebooks_items or []
        self.urls: list[str] = []
        self.googlebooks_queries: list[tuple[str, int]] = []

    async def _api_request(self, url: str) -> dict[str, Any]:
        self.urls.append(url)
        return {"docs": self.docs}

    async def _googlebooks_request(self, *, query: str, limit: int) -> dict[str, Any]:
        self.googlebooks_queries.append((query, limit))
        return {"items": self.googlebooks_items}


def test_validate_author_is_diacritics_safe_and_suppresses_noop_suggestion() -> None:
    plugin = _FakeOpenLibrary(
        docs=[
            {
                "author_name": [
                    "Jozef Ciger Hronsky",
                    "Jozef C\u00edger Hronsk\u00fd",
                ]
            }
        ]
    )

    result = asyncio.run(
        plugin.execute_job(plugin.build_validate_author_job("Jozef Ciger Hronsky"))
    )

    assert result == {
        "valid": True,
        "canonical": "Jozef Ciger Hronsky",
        "suggestion": None,
    }
    assert plugin.urls == [
        "https://openlibrary.org/search.json?author=Jozef+Ciger+Hronsky&limit=20"
    ]


def test_validate_book_is_diacritics_safe_and_lookup_returns_metadata() -> None:
    plugin = _FakeOpenLibrary(
        docs=[
            {
                "key": "/works/OL1W",
                "title": "P\u00edsali\u010dek",
                "author_name": ["Jozef C\u00edger Hronsk\u00fd"],
                "first_publish_year": 1934,
                "publisher": ["Matica"],
                "isbn": ["1234567890"],
                "language": ["slk"],
                "cover_i": 42,
                "subject": ["children"],
                "ebook_access": "borrowable",
            },
            {
                "key": "/works/OL2W",
                "title": "Ina Kniha",
                "author_name": ["Ina Autorka"],
            },
        ]
    )

    result = asyncio.run(
        plugin.execute_job(plugin.build_validate_book_job("Jozef Ciger Hronsky", "Pisalicek"))
    )
    metadata = asyncio.run(
        plugin.execute_job(plugin.build_lookup_book_job("Jozef Ciger Hronsky", "Pisalicek"))
    )

    assert result == {
        "valid": True,
        "canonical": {
            "author": "Jozef C\u00edger Hronsk\u00fd",
            "title": "P\u00edsali\u010dek",
        },
        "suggestion": None,
    }
    assert metadata == {
        "title": "P\u00edsali\u010dek",
        "authors": ["Jozef C\u00edger Hronsk\u00fd"],
        "author": "Jozef C\u00edger Hronsk\u00fd",
        "year": 1934,
        "publisher": "Matica",
        "isbn": "1234567890",
        "language": "slk",
        "cover_url": "https://covers.openlibrary.org/b/id/42-L.jpg",
        "subjects": ["children"],
        "ebook_access": "borrowable",
    }


def test_validate_book_returns_deterministic_suggestion() -> None:
    plugin = _FakeOpenLibrary(
        docs=[
            {
                "key": "/works/OL3W",
                "title": "Harry Potter and the Philosopher's Stone",
                "author_name": ["J. K. Rowling"],
            },
            {
                "key": "/works/OL4W",
                "title": "Harry Potter and the Chamber of Secrets",
                "author_name": ["J. K. Rowling"],
            },
        ]
    )

    result = asyncio.run(
        plugin.execute_job(
            plugin.build_validate_book_job(
                "J. K. Roling",
                "Harry Potter and the Philosopher Stone",
            )
        )
    )

    assert result == {
        "valid": False,
        "canonical": None,
        "suggestion": {
            "author": "J. K. Rowling",
            "title": "Harry Potter and the Philosopher's Stone",
        },
    }


def test_validate_book_uses_googlebooks_title_fallback_when_openlibrary_misses() -> None:
    plugin = _FakeOpenLibrary(
        docs=[],
        googlebooks_items=[
            {
                "id": "gb2",
                "volumeInfo": {
                    "title": "Harry Potter and the Chamber of Secrets",
                    "authors": ["J. K. Rowling"],
                },
            },
            {
                "id": "gb1",
                "volumeInfo": {
                    "title": "Harry Potter and the Philosopher's Stone",
                    "authors": ["J. K. Rowling"],
                },
            },
        ],
    )

    result = asyncio.run(
        plugin.execute_job(
            plugin.build_validate_book_job(
                "J. K. Rowling",
                "Harry Potter and the Philosopher Stone",
            )
        )
    )

    assert result == {
        "valid": False,
        "canonical": None,
        "suggestion": {
            "author": "J. K. Rowling",
            "title": "Harry Potter and the Philosopher's Stone",
        },
    }
    assert plugin.googlebooks_queries == [
        (
            "inauthor:J. K. Rowling+intitle:Harry Potter and the Philosopher Stone",
            20,
        )
    ]


def test_execute_request_phase1_validation_returns_provider_payload() -> None:
    plugin = _FakeOpenLibrary(
        docs=[
            {
                "author_name": ["J. K. Rowling"],
                "title": "Harry Potter and the Philosopher's Stone",
            }
        ],
        googlebooks_items=[
            {
                "id": "gb1",
                "volumeInfo": {
                    "title": "Harry Potter and the Philosopher's Stone",
                    "authors": ["J. K. Rowling"],
                },
            }
        ],
    )

    result = asyncio.run(
        plugin.execute_job(
            plugin.build_phase1_validation_job(
                "J. K. Roling",
                "Harry Potter and the Philosopher Stone",
            )
        )
    )

    assert result == {
        "provider": "metadata_openlibrary",
        "author": {
            "valid": False,
            "canonical": None,
            "suggestion": "J. K. Rowling",
        },
        "book": {
            "valid": False,
            "canonical": None,
            "suggestion": {
                "author": "J. K. Rowling",
                "title": "Harry Potter and the Philosopher's Stone",
            },
        },
    }


def test_metadata_openlibrary_exposes_public_request_and_job_surfaces() -> None:
    plugin = _FakeOpenLibrary(docs=[])

    assert hasattr(plugin, "execute_request")
    assert hasattr(plugin, "execute_job")
    assert not hasattr(plugin, "validate_author")
    assert not hasattr(plugin, "validate_book")
    assert not hasattr(plugin, "lookup_book")
    assert not hasattr(plugin, "fetch")


def test_execute_request_accepts_real_public_request_builder() -> None:
    plugin = _FakeOpenLibrary(
        docs=[
            {
                "author_name": ["J. K. Rowling"],
                "title": "Harry Potter and the Philosopher's Stone",
            }
        ],
        googlebooks_items=[
            {
                "id": "gb1",
                "volumeInfo": {
                    "title": "Harry Potter and the Philosopher's Stone",
                    "authors": ["J. K. Rowling"],
                },
            }
        ],
    )

    result = asyncio.run(
        plugin.execute_request(
            plugin.build_phase1_validation_request(
                "J. K. Roling",
                "Harry Potter and the Philosopher Stone",
            )
        )
    )

    assert result == {
        "provider": "metadata_openlibrary",
        "author": {
            "valid": False,
            "canonical": None,
            "suggestion": "J. K. Rowling",
        },
        "book": {
            "valid": False,
            "canonical": None,
            "suggestion": {
                "author": "J. K. Rowling",
                "title": "Harry Potter and the Philosopher's Stone",
            },
        },
    }


def test_execute_request_rejects_unknown_operation() -> None:
    plugin = _FakeOpenLibrary(docs=[])

    try:
        asyncio.run(
            plugin.execute_job(
                {
                    "job_type": plugin.JOB_TYPE,
                    "job_version": plugin.JOB_VERSION,
                    "provider": "metadata_openlibrary",
                    "request": {
                        "request_version": plugin.REQUEST_VERSION,
                        "operation": "unknown",
                        "payload": {},
                    },
                }
            )
        )
    except Exception as exc:
        assert str(exc) == "Unsupported operation: unknown"
    else:
        raise AssertionError("expected metadata job executor to reject unknown operation")


def test_metadata_boundary_routes_phase1_validation_via_explicit_job_boundary(
    monkeypatch,
) -> None:
    boundary = __import__("plugins.import.metadata_boundary", fromlist=["validate_author_title"])
    docs = [
        {
            "author_name": ["J. K. Rowling"],
            "title": "Harry Potter and the Philosopher's Stone",
        }
    ]
    googlebooks_items = [
        {
            "id": "gb1",
            "volumeInfo": {
                "title": "Harry Potter and the Philosopher's Stone",
                "authors": ["J. K. Rowling"],
            },
        }
    ]
    seen: dict[str, object] = {}
    urls: list[str] = []
    googlebooks_queries: list[tuple[str, int]] = []

    async def _api_request(self, url: str) -> dict[str, Any]:
        urls.append(url)
        return {"docs": docs}

    async def _googlebooks_request(self, *, query: str, limit: int) -> dict[str, Any]:
        googlebooks_queries.append((query, limit))
        return {"items": googlebooks_items}

    async def _execute_job(self, job: dict[str, Any]) -> dict[str, Any]:
        seen["job"] = dict(job)
        request = dict(job.get("request") or {})
        return await OpenLibraryPlugin._execute_request(self, request)

    async def _private_execute_job(self, _job: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("metadata boundary must not call private provider runner")

    boundary.validate_author_title.cache_clear()
    _builder, plugin = boundary._resolve_phase1_validation_authority()
    monkeypatch.setattr(plugin, "_api_request", _api_request.__get__(plugin, type(plugin)))
    monkeypatch.setattr(
        plugin,
        "_googlebooks_request",
        _googlebooks_request.__get__(plugin, type(plugin)),
    )
    monkeypatch.setattr(plugin, "execute_job", _execute_job.__get__(plugin, type(plugin)))
    monkeypatch.setattr(plugin, "_execute_job", _private_execute_job.__get__(plugin, type(plugin)))

    author_result, book_result = boundary.validate_author_title(
        "J. K. Roling",
        "Harry Potter and the Philosopher Stone",
    )

    assert isinstance(seen["job"], dict)
    assert seen["job"]["request"]["operation"] == "phase1_validate"
    assert author_result == {
        "valid": False,
        "canonical": None,
        "suggestion": "J. K. Rowling",
    }
    assert book_result == {
        "valid": False,
        "canonical": None,
        "suggestion": {
            "author": "J. K. Rowling",
            "title": "Harry Potter and the Philosopher's Stone",
        },
    }


def test_metadata_boundary_uses_two_second_timeout() -> None:
    boundary = __import__(
        "plugins.import.metadata_boundary",
        fromlist=["_resolve_phase1_validation_authority"],
    )

    _builder, plugin = boundary._resolve_phase1_validation_authority()

    assert plugin.timeout_seconds == pytest.approx(2.0)


def test_openlibrary_http_cache_reuses_rate_limited_result(monkeypatch) -> None:
    OpenLibraryPlugin._cached_http_result.cache_clear()
    calls = {"count": 0}

    def _fake_urlopen(_request, timeout):
        del timeout
        calls["count"] += 1
        raise HTTPError(
            url="https://openlibrary.org/search.json?author=A&limit=20",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("plugins.metadata_openlibrary.plugin.urlopen", _fake_urlopen)

    for _ in range(2):
        try:
            OpenLibraryPlugin._http_get_json(
                url="https://openlibrary.org/search.json?author=A&limit=20",
                timeout_seconds=2.0,
                max_response_bytes=1024,
            )
        except Exception as exc:
            assert str(exc) == "API request failed: HTTP 429"
        else:
            raise AssertionError("expected cached HTTP 429 failure")

    assert calls["count"] == 1


def test_metadata_boundary_source_uses_registry_callable_authority_only() -> None:
    source = Path("plugins/import/metadata_boundary.py").read_text(encoding="utf-8")

    assert 'resolve_import_plugin(plugin_name="metadata_openlibrary")' not in source
    assert 'getattr(plugin, "build_phase1_validation_job", None)' not in source
    assert 'getattr(plugin, "execute_job", None)' not in source
    assert 'getattr(plugin, "_execute_job", None)' not in source
    assert "asyncio.run" not in source
    assert "threading.Thread" not in source
    assert '"metadata.phase1_validate"' in source
    assert "resolve_wizard_callable(" in source
    assert "resolve_registered_wizard_callable(" in source


def test_metadata_openlibrary_manifest_points_to_provider_owned_callable_contract() -> None:
    source = Path("plugins/metadata_openlibrary/plugin.yaml").read_text(encoding="utf-8")

    assert "wizard_callable_manifest_pointer: wizard_callable_manifest.json" in source


def test_metadata_openlibrary_publishes_phase1_validation_callable_manifest() -> None:
    manifest = json.loads(
        Path("plugins/metadata_openlibrary/wizard_callable_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest == {
        "schema_version": 1,
        "operations": [
            {
                "operation_id": "metadata.phase1_validate",
                "method_name": "build_phase1_validation_job",
                "execution_mode": "job",
            }
        ],
    }
