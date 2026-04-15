from __future__ import annotations

import gc
import json
import sys
import warnings
from importlib import import_module
from pathlib import Path

import pytest


def _ensure_src_on_path() -> None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "src"
        if candidate.is_dir():
            sys.path.insert(0, str(candidate))
            return


_ensure_src_on_path()

_HAS_SRC_TREE = any((parent / "src").is_dir() for parent in Path(__file__).resolve().parents)
if not _HAS_SRC_TREE:
    pytestmark = pytest.mark.skip(reason="src tree unavailable for isolated validator test run")


if _HAS_SRC_TREE:
    from audiomason.core.config import ConfigResolver

    ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
    atomic_write_json = import_module("plugins.import.storage").atomic_write_json
else:  # pragma: no cover - isolated validator tree
    ConfigResolver = object  # type: ignore[assignment]
    ImportWizardEngine = object
    atomic_write_json = None
if _HAS_SRC_TREE:
    RootName = import_module("plugins.file_io.service.types").RootName
    WIZARD_DEFINITION_REL_PATH = import_module(
        "plugins.import.wizard_definition_model"
    ).WIZARD_DEFINITION_REL_PATH
    build_default_wizard_definition_v3 = import_module(
        "plugins.import.dsl.default_wizard_v3"
    ).build_default_wizard_definition_v3
else:  # pragma: no cover - isolated validator tree
    RootName = object
    WIZARD_DEFINITION_REL_PATH = ""
    build_default_wizard_definition_v3 = None


def _install_phase1_metadata_callable(
    monkeypatch,
    *,
    result: dict[str, object] | None = None,
    exc: Exception | None = None,
) -> None:
    call_v1 = import_module("plugins.import.primitives.call_v1")

    class _Plugin:
        async def execute_job(self, job: dict[str, object]) -> dict[str, object]:
            request_any = job.get("request")
            request = dict(request_any) if isinstance(request_any, dict) else {}
            payload_any = request.get("payload")
            payload = dict(payload_any) if isinstance(payload_any, dict) else {}
            assert request.get("operation") == "phase1_validate"
            assert "author" in payload
            assert "title" in payload
            if exc is not None:
                raise exc
            assert result is not None
            if callable(result):
                return dict(result(author=str(payload["author"]), title=str(payload["title"])))
            return dict(result)

    def _build_job(*, author: str, title: str) -> dict[str, object]:
        return {
            "job_type": "metadata_openlibrary.request",
            "job_version": 1,
            "provider": "metadata_openlibrary",
            "request": {
                "request_version": 1,
                "operation": "phase1_validate",
                "payload": {"author": author, "title": title},
            },
        }

    monkeypatch.setattr(
        call_v1,
        "_resolve_published_callable_binding",
        lambda **_: call_v1._ResolvedCallableBinding(
            operation_id="metadata.phase1_validate",
            execution_mode="job",
            plugin_obj=_Plugin(),
            callable_obj=_build_job,
        ),
    )


def _make_engine(tmp_path: Path) -> tuple[ImportWizardEngine, dict[str, Path]]:
    roots = {
        name: tmp_path / name for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards")
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    defaults = {
        "file_io": {
            "roots": {
                "inbox_dir": str(roots["inbox"]),
                "stage_dir": str(roots["stage"]),
                "outbox_dir": str(roots["outbox"]),
                "jobs_dir": str(roots["jobs"]),
                "config_dir": str(roots["config"]),
                "wizards_dir": str(roots["wizards"]),
            }
        },
        "output_dir": str(roots["outbox"]),
        "diagnostics": {"enabled": False},
    }
    resolver = ConfigResolver(
        cli_args=defaults,
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    engine = ImportWizardEngine(resolver=resolver)
    atomic_write_json(
        engine.get_file_service(),
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        build_default_wizard_definition_v3(),
    )
    return engine, roots


def _write_book(root: Path, author: str, book: str, filename: str = "track01.mp3") -> None:
    book_dir = root / author / book
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / filename).write_text("x", encoding="utf-8")


def test_create_session_autofills_single_author_and_single_book(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "Author", "Book")

    state = engine.create_session("inbox", "", mode="stage")

    assert state["current_step_id"] == "effective_author"
    assert state["answers"]["select_authors"]["selection_expr"] == "1"
    assert state["answers"]["select_books"]["selection_expr"] == "1"
    assert state["vars"]["phase1"]["metadata"]["values"] == {
        "title": "Book",
        "artist": "Author",
        "album": "Book",
        "album_artist": "Author",
    }
    assert state["vars"]["phase1"]["cover"]["mode"] == "skip"
    assert state["vars"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Author",
        "title": "Book",
    }
    assert state["vars"]["runtime"]["detached_runtime"]["file_io"]["roots"]["inbox_dir"] == str(
        roots["inbox"]
    )
    assert state["vars"]["phase1"]["policy"]["publish_policy"] == {"target_root": "stage"}


def test_multi_book_author_and_title_edit_apply_per_book(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "Author", "Book1")
    _write_book(roots["inbox"], "Author", "Book2")
    _install_phase1_metadata_callable(
        monkeypatch,
        result=lambda *, author, title: {
            "provider": "metadata_openlibrary",
            "author": {"value": author, "canonical": author, "valid": True},
            "book": {"value": title, "canonical": title, "valid": True},
        },
    )

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])

    if state["current_step_id"] == "select_authors":
        state = engine.submit_step(session_id, "select_authors", {"selection": "1"})
        assert state["current_step_id"] == "select_books"
    else:
        assert state["current_step_id"] == "select_books"

    state = engine.submit_step(session_id, "select_books", {"selection": "all"})
    assert state["current_step_id"] == "effective_author"

    state = engine.submit_step(session_id, "effective_author", {"value": "Canonical Author"})
    assert state["current_step_id"] == "effective_title"

    state = engine.submit_step(session_id, "effective_title", {"value": "Canonical Title"})
    assert state["current_step_id"] == "covers_policy_mode"

    authority_by_book = state["vars"]["phase1"]["metadata"]["authority_by_book"]
    titles = {book["book_label"] for book in authority_by_book.values()}
    authors = {book["author_label"] for book in authority_by_book.values()}
    assert titles == {"Canonical Title"}
    assert authors == {"Canonical Author"}


def test_metadata_projection_applies_multi_book_title_override_per_book(tmp_path: Path) -> None:
    del tmp_path
    phase1_metadata = import_module("plugins.import.phase1_metadata_flow")

    projection = phase1_metadata.build_phase1_metadata_projection(
        source_projection={
            "book_meta": {
                "book:1": {
                    "author_label": "Author",
                    "book_label": "Book1",
                    "source_relative_path": "Author/Book1",
                },
                "book:2": {
                    "author_label": "Author",
                    "book_label": "Book2",
                    "source_relative_path": "Author/Book2",
                },
            },
            "select_books": {
                "selected_ids": ["book:1", "book:2"],
                "selected_source_relative_paths": ["Author/Book1", "Author/Book2"],
            },
        },
        state={
            "answers": {
                "effective_author": {"author": "Canonical Author"},
                "effective_title": {"title": "Canonical Title"},
            }
        },
    )

    authority_by_book = projection["authority_by_book"]
    assert {book["author_label"] for book in authority_by_book.values()} == {"Canonical Author"}
    assert {book["book_label"] for book in authority_by_book.values()} == {"Canonical Title"}


def test_metadata_projection_multi_book_prompt_prefill_omits_first_title_bias(
    tmp_path: Path,
) -> None:
    del tmp_path
    phase1_metadata = import_module("plugins.import.phase1_metadata_flow")

    projection = phase1_metadata.build_phase1_metadata_projection(
        source_projection={
            "book_meta": {
                "book:1": {
                    "author_label": "Author",
                    "book_label": "Book1",
                    "source_relative_path": "Author/Book1",
                },
                "book:2": {
                    "author_label": "Author",
                    "book_label": "Book2",
                    "source_relative_path": "Author/Book2",
                },
            },
            "select_books": {
                "selected_ids": ["book:1", "book:2"],
                "selected_source_relative_paths": ["Author/Book1", "Author/Book2"],
            },
        },
        state={"answers": {}},
    )

    assert projection["author_prompt_prefill"] == "Author"
    assert projection["title_prompt_prefill"] is None
    assert projection["title_prompt_hint"].startswith(
        "Multiple selected books have different titles."
    )
    assert projection["title_prompt_examples"][:2] == ["Book1", "Book2"]


def test_multi_book_author_edit_keeps_distinct_titles_until_title_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "Author", "Book1")
    _write_book(roots["inbox"], "Author", "Book2")
    _install_phase1_metadata_callable(
        monkeypatch,
        result=lambda *, author, title: {
            "provider": "metadata_openlibrary",
            "author": {"value": author, "canonical": author, "valid": True},
            "book": {"value": title, "canonical": title, "valid": True},
        },
    )

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    if state["current_step_id"] == "select_authors":
        state = engine.submit_step(session_id, "select_authors", {"selection": "1"})
    state = engine.submit_step(session_id, "select_books", {"selection": "all"})
    state = engine.submit_step(session_id, "effective_author", {"value": "Canonical Author"})

    assert state["current_step_id"] == "effective_title"
    authority_by_book = state["vars"]["phase1"]["metadata"]["authority_by_book"]
    assert {book["author_label"] for book in authority_by_book.values()} == {"Canonical Author"}
    assert {book["book_label"] for book in authority_by_book.values()} == {"Book1", "Book2"}
    assert state["vars"]["phase1"]["metadata"]["title_prompt_prefill"] is None


def test_metadata_projection_prefers_explicit_validation_answer_over_hidden_boundary() -> None:
    phase1_metadata = import_module("plugins.import.phase1_metadata_flow")

    def _unexpected_validate(*, author: str, title: str):
        raise AssertionError(f"hidden validation fallback used for {author}/{title}")

    phase1_metadata._openlibrary_validate.cache_clear()
    original = phase1_metadata._validated_author_title
    phase1_metadata._validated_author_title = _unexpected_validate
    try:
        projection = phase1_metadata.build_phase1_metadata_projection(
            source_projection={
                "book_meta": {
                    "book:1": {
                        "author_label": "Meyrink, Gustav (audio) [mp3]",
                        "book_label": "Gustav Meyrink - Preparat (2h59m)",
                        "source_relative_path": "A/B",
                    }
                },
                "select_books": {
                    "selected_ids": ["book:1"],
                    "selected_source_relative_paths": ["A/B"],
                },
            },
            state={
                "answers": {
                    "metadata_validate_initial": {
                        "result": {
                            "provider": "metadata_openlibrary",
                            "author": {
                                "valid": False,
                                "canonical": None,
                                "suggestion": "Gustav Meyrink",
                            },
                            "book": {
                                "valid": False,
                                "canonical": None,
                                "suggestion": {
                                    "author": "Gustav Meyrink",
                                    "title": "Preparat",
                                },
                            },
                        }
                    }
                }
            },
        )
    finally:
        phase1_metadata._validated_author_title = original

    assert projection["normalize_author"] == "Gustav Meyrink"
    assert projection["normalize_book_title"] == "Preparat"
    assert projection["validation"]["provider"] == "metadata_openlibrary"
    assert projection["author_prompt_hint"] == "Metadata lookup suggested canonical author/title."
    assert projection["author_prompt_examples"] == ["Gustav Meyrink"]
    assert projection["title_prompt_examples"] == ["Preparat"]


def test_metadata_projection_normalizes_source_labels_without_lookup() -> None:
    phase1_metadata = import_module("plugins.import.phase1_metadata_flow")

    projection = phase1_metadata.build_phase1_metadata_projection(
        source_projection={
            "book_meta": {
                "book:1": {
                    "author_label": "Meyrink, Gustav (audio) [mp3]",
                    "book_label": "Gustav Meyrink - Preparat a dalsi povidky (2h59m)",
                    "source_relative_path": "A/B",
                }
            },
            "select_books": {
                "selected_ids": ["book:1"],
                "selected_source_relative_paths": ["A/B"],
            },
        },
        state={"answers": {}},
    )

    assert projection["source_author"] == "Gustav Meyrink"
    assert projection["book_title"] == "Preparat a dalsi povidky"
    assert projection["normalize_author"] == "Gustav Meyrink"
    assert projection["normalize_book_title"] == "Preparat a dalsi povidky"
    assert projection["author_prompt_hint"] == "Metadata lookup not available."


def test_select_authors_refreshes_filtered_book_defaults_for_two_pass_flow(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A", "Book1")
    _write_book(roots["inbox"], "A", "Book2")
    _write_book(roots["inbox"], "B", "Book3")

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    state = engine.submit_step(session_id, "select_authors", {"selection": "1"})

    assert state["current_step_id"] == "select_books"
    assert state["vars"]["phase1"]["select_books"]["selection_expr"] == "all"
    assert state["vars"]["phase1"]["select_books"]["selected_source_relative_paths"] == [
        "A/Book1",
        "A/Book2",
    ]


def test_load_state_repairs_missing_phase1_projection_on_resume(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "Author", "Book")

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    state_path = roots["wizards"] / "import" / "sessions" / session_id / "state.json"
    stored = json.loads(state_path.read_text(encoding="utf-8"))
    stored["vars"] = {}
    state_path.write_text(json.dumps(stored), encoding="utf-8")

    repaired = engine.get_state(session_id)

    assert repaired["vars"]["phase1"]["select_authors"]["selection_expr"] == "1"
    assert repaired["vars"]["phase1"]["select_books"]["selection_expr"] == "1"


def test_create_session_uses_metadata_validation_and_explicit_cover_choice(
    monkeypatch, tmp_path: Path
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A", "Book")

    phase1_cover = import_module("plugins.import.phase1_cover_flow")
    _install_phase1_metadata_callable(
        monkeypatch,
        result={
            "provider": "metadata_openlibrary",
            "author": {"valid": False, "canonical": None, "suggestion": "Author A"},
            "book": {
                "valid": False,
                "canonical": None,
                "suggestion": {"author": "Author A", "title": "Canonical Book"},
            },
        },
    )

    def _fake_discover(
        self,
        directory: Path,
        *,
        audio_file: Path | None = None,
        group_root: str | None = None,
    ):
        assert directory == roots["inbox"] / "A" / "Book"
        assert audio_file == roots["inbox"] / "A" / "Book" / "track01.mp3"
        assert group_root == "inbox"
        return [
            {
                "kind": "file",
                "candidate_id": "file:canonical-cover.png",
                "apply_mode": "copy",
                "path": str(directory / "canonical-cover.png"),
                "mime_type": "image/png",
                "cache_key": "file:canonical-cover.png",
                "root_name": group_root or "",
            }
        ]

    def _fake_discover_boundary(
        *,
        fs,
        source_root,
        source_prefix,
        source_relative_path,
        group_root,
        plugin=None,
    ):
        del fs, source_root, plugin
        assert source_prefix == ""
        assert source_relative_path == "A/Book"
        assert group_root == "inbox"
        return [
            {
                "kind": "file",
                "candidate_id": "file:canonical-cover.png",
                "apply_mode": "copy",
                "path": "A/Book/canonical-cover.png",
                "candidate_relative_path": "A/Book/canonical-cover.png",
                "mime_type": "image/png",
                "cache_key": "file:canonical-cover.png",
                "root_name": group_root or "",
                "source_root": "inbox",
                "source_relative_path": source_relative_path,
            }
        ]

    monkeypatch.setattr(phase1_cover, "discover_cover_candidates", _fake_discover_boundary)

    state = engine.create_session("inbox", "", mode="stage")

    assert state["vars"]["phase1"]["metadata"]["validation"]["provider"] == "metadata_openlibrary"
    assert state["vars"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Author A",
        "title": "Canonical Book",
    }
    assert state["vars"]["phase1"]["cover"]["choice"] == {
        "kind": "candidate",
        "candidate_id": "file:canonical-cover.png",
        "source_relative_path": "A/Book",
    }
    assert state["vars"]["phase1"]["runtime"]["covers_policy"]["candidates"][0]["candidate_id"] == (
        "file:canonical-cover.png"
    )
    assert state["vars"]["phase1"]["runtime"]["covers_policy"]["candidates"][0]["path"] == (
        "A/Book/canonical-cover.png"
    )


def test_cover_projection_prefers_explicit_discovery_answer_over_hidden_boundary() -> None:
    phase1_cover = import_module("plugins.import.phase1_cover_flow")

    def _unexpected_discover(**_: object):
        raise AssertionError("hidden cover discovery fallback used")

    original = phase1_cover.discover_cover_candidates
    phase1_cover.discover_cover_candidates = _unexpected_discover
    try:
        projection = phase1_cover.build_phase1_cover_projection(
            discovery=[],
            source_projection={
                "select_books": {
                    "selected_source_relative_paths": ["A/B"],
                }
            },
            state={
                "answers": {
                    "cover_discover_initial": {
                        "result": [
                            {
                                "kind": "file",
                                "candidate_id": "file:cover.jpg",
                                "source_relative_path": "A/B",
                            }
                        ]
                    }
                },
                "source": {"root": "inbox", "relative_path": ""},
            },
            fs=None,
        )
    finally:
        phase1_cover.discover_cover_candidates = original

    assert projection["allowed_modes"] == ["file", "skip", "url"]
    assert projection["has_single_candidate"] is True
    assert projection["choice"] == {
        "kind": "candidate",
        "candidate_id": "file:cover.jpg",
        "source_relative_path": "A/B",
    }


def test_default_v3_phase1_runtime_step_uses_flow_visible_runtime_projection() -> None:
    definition = build_default_wizard_definition_v3()
    phase1_node = next(
        node for node in definition["nodes"] if node["step_id"] == "phase1_runtime_defaults"
    )
    op = phase1_node["op"]

    assert op["primitive_id"] == "data.set"
    assert op["inputs"] == {}
    assert op["writes"] == []


async def test_create_session_under_running_loop_awaits_metadata_validation_without_warning(
    monkeypatch, tmp_path: Path
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A", "Book")
    _install_phase1_metadata_callable(
        monkeypatch,
        result={
            "provider": "metadata_openlibrary",
            "author": {"valid": False, "canonical": None, "suggestion": "Author A"},
            "book": {
                "valid": False,
                "canonical": None,
                "suggestion": {"author": "Author A", "title": "Canonical Book"},
            },
        },
    )

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        state = engine.create_session("inbox", "", mode="stage")
        gc.collect()

    assert not any("was never awaited" in str(item.message) for item in seen)
    assert state["vars"]["phase1"]["metadata"]["validation"] == {
        "provider": "metadata_openlibrary",
        "author": {"valid": False, "canonical": None, "suggestion": "Author A"},
        "book": {
            "valid": False,
            "canonical": None,
            "suggestion": {"author": "Author A", "title": "Canonical Book"},
        },
    }
    assert state["vars"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Author A",
        "title": "Canonical Book",
    }


async def test_resume_repair_under_running_loop_rebuilds_phase1_without_warning(
    monkeypatch, tmp_path: Path
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A", "Book")
    _install_phase1_metadata_callable(
        monkeypatch,
        result={
            "provider": "metadata_openlibrary",
            "author": {"valid": False, "canonical": None, "suggestion": "Author A"},
            "book": {
                "valid": False,
                "canonical": None,
                "suggestion": {"author": "Author A", "title": "Canonical Book"},
            },
        },
    )

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    state_path = roots["wizards"] / "import" / "sessions" / session_id / "state.json"
    stored = json.loads(state_path.read_text(encoding="utf-8"))
    stored["vars"] = {}
    state_path.write_text(json.dumps(stored), encoding="utf-8")

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        repaired = engine.create_session("inbox", "", mode="stage")
        gc.collect()

    assert not any("was never awaited" in str(item.message) for item in seen)
    assert repaired["vars"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Author A",
        "title": "Canonical Book",
    }
    assert repaired["vars"]["phase1"]["metadata"]["validation"]["provider"] == (
        "metadata_openlibrary"
    )


async def test_create_session_under_running_loop_keeps_fallback_on_validation_failure(
    monkeypatch, tmp_path: Path
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "Author", "Book")
    _install_phase1_metadata_callable(monkeypatch, exc=RuntimeError("offline"))

    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        state = engine.create_session("inbox", "", mode="stage")
        gc.collect()

    assert not any("was never awaited" in str(item.message) for item in seen)
    assert state["vars"]["phase1"]["metadata"]["validation"] == {}
    assert state["vars"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Author",
        "title": "Book",
    }
    assert state["answers"]["metadata_validate_initial"]["error"] == {
        "type": "RuntimeError",
        "message": "offline",
    }
    assert state["vars"]["phase1"]["metadata"]["author_prompt_hint"] == (
        "Metadata lookup failed: offline"
    )
