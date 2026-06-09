from __future__ import annotations

import json
import sys
from collections.abc import Generator
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
else:
    pytestmark = pytest.mark.timeout(0)


if _HAS_SRC_TREE:
    from audiomason.core.config import ConfigResolver
    from audiomason.core.logging import VerbosityLevel, get_verbosity, set_verbosity

    ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
    atomic_write_json = import_module("plugins.import.storage").atomic_write_json

    _PREVIOUS_VERBOSITY = get_verbosity()

    @pytest.fixture(autouse=True)
    def _quiet_logging() -> Generator[None, None, None]:
        set_verbosity(VerbosityLevel.QUIET)
        yield
        set_verbosity(_PREVIOUS_VERBOSITY)
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
    original_resolver = call_v1._resolve_published_callable_binding

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

    def _resolve_binding(*, operation_id: str, expected_execution_mode: str):
        if operation_id != "metadata.phase1_validate":
            return original_resolver(
                operation_id=operation_id,
                expected_execution_mode=expected_execution_mode,
            )
        return call_v1._ResolvedCallableBinding(
            operation_id="metadata.phase1_validate",
            execution_mode="job",
            plugin_obj=_Plugin(),
            callable_obj=_build_job,
        )

    monkeypatch.setattr(call_v1, "_resolve_published_callable_binding", _resolve_binding)


def _install_fast_phase1_validation(monkeypatch) -> None:
    metadata_boundary = import_module("plugins.import.metadata_boundary")

    class _ValidatedAuthorTitle:
        def __call__(self, author: str, title: str) -> tuple[dict[str, object], dict[str, object]]:
            return (
                {
                    "valid": False,
                    "canonical": None,
                    "suggestion": author,
                },
                {
                    "valid": False,
                    "canonical": None,
                    "suggestion": {"author": author, "title": title},
                },
            )

        def cache_clear(self) -> None:
            return None

    monkeypatch.setattr(
        metadata_boundary,
        "validate_author_title",
        _ValidatedAuthorTitle(),
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

    assert state["current_step_id"] == "effective_author_item"
    assert state["answers"]["select_authors"]["selection_expr"] == "all"
    assert state["answers"]["select_books"]["selection_expr"] == "all"
    assert state["vars"]["phase1"]["select_authors"]["selected_ids"] == ["author:Author"]
    assert state["vars"]["phase1"]["select_books"]["selected_source_relative_paths"] == [
        "Author/Book"
    ]
    assert state["vars"]["phase1"]["cover"]["mode"] == "per_book"
    assert state["vars"]["runtime"]["detached_runtime"]["file_io"]["roots"]["inbox_dir"] == str(
        roots["inbox"]
    )
    assert state["vars"]["phase1"]["policy"]["publish_policy"] == {"target_root": "stage"}


@pytest.mark.timeout(0)
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

    _install_fast_phase1_validation(monkeypatch)

    state = engine.submit_step(session_id, "select_books", {"selection": "all"})
    assert state["current_step_id"] == "effective_author_item"

    state = engine.submit_step(session_id, "effective_author_item", {"value": "Canonical Author"})
    assert state["current_step_id"] == "effective_title_item"

    state = engine.submit_step(session_id, "effective_title_item", {"value": "Canonical Title"})
    assert state["current_step_id"] == "effective_title_item"

    state = engine.submit_step(session_id, "effective_title_item", {"value": "Canonical Title"})
    assert state["current_step_id"] == "covers_policy_mode"

    assert state["answers"]["store_author_item"] == {"author": "Canonical Author"}
    assert state["answers"]["store_title_item"] == {"title": "Canonical Title"}
    assert state["vars"]["phase1"]["metadata"]["filename_policy"] == {
        "author": "Canonical Author",
        "title": "Canonical Title",
    }
    assert state["vars"]["phase1"]["metadata"]["values"] == {
        "album": "Canonical Title",
        "album_artist": "Canonical Author",
        "artist": "Canonical Author",
        "title": "Canonical Title",
    }


def test_multi_author_loop_keeps_per_author_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "AuthorOne", "Book1")
    _write_book(roots["inbox"], "AuthorTwo", "Book2")
    _install_fast_phase1_validation(monkeypatch)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])

    if state["current_step_id"] == "select_authors":
        state = engine.submit_step(session_id, "select_authors", {"selection": "all"})
        assert state["current_step_id"] == "select_books"
    else:
        assert state["current_step_id"] == "select_books"

    state = engine.submit_step(session_id, "select_books", {"selection": "all"})
    assert state["current_step_id"] == "effective_author_item"

    state = engine.submit_step(session_id, "effective_author_item", {"value": "Author One Canon"})
    assert state["current_step_id"] == "effective_author_item"

    state = engine.submit_step(session_id, "effective_author_item", {"value": "Author Two Canon"})
    assert state["current_step_id"] == "effective_title_item"

    state = engine.submit_step(session_id, "effective_title_item", {"value": "Book One Canon"})
    assert state["current_step_id"] == "effective_title_item"

    state = engine.submit_step(session_id, "effective_title_item", {"value": "Book Two Canon"})
    assert state["current_step_id"] == "covers_policy_mode"

    assert state["answers"]["store_author_item"] == {"author": "Author Two Canon"}
    assert state["answers"]["store_title_item"] == {"title": "Book Two Canon"}
    assert state["vars"]["phase1"]["metadata"]["filename_policy"] == {
        "author": "Author Two Canon",
        "title": "Book Two Canon",
    }
    assert state["vars"]["phase1"]["metadata"]["values"] == {
        "album": "Book Two Canon",
        "album_artist": "Author Two Canon",
        "artist": "Author Two Canon",
        "title": "Book Two Canon",
    }


def test_per_item_author_title_edits_are_authoritative_over_validation_suggestions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A1", "B1")
    _write_book(roots["inbox"], "A2", "B2")
    _install_phase1_metadata_callable(
        monkeypatch,
        result=lambda *, author, title: {
            "provider": "metadata_openlibrary",
            "author": {"value": author, "canonical": "SERVER_AUTHOR", "valid": True},
            "book": {"value": title, "canonical": "SERVER_TITLE", "valid": True},
        },
    )
    _install_fast_phase1_validation(monkeypatch)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    if state["current_step_id"] == "select_authors":
        state = engine.submit_step(session_id, "select_authors", {"selection": "all"})
    state = engine.submit_step(session_id, "select_books", {"selection": "all"})

    state = engine.submit_step(session_id, "effective_author_item", {"value": "User Author One"})
    state = engine.submit_step(session_id, "effective_author_item", {"value": "User Author Two"})
    state = engine.submit_step(session_id, "effective_title_item", {"value": "User Book One"})
    state = engine.submit_step(session_id, "effective_title_item", {"value": "User Book Two"})

    assert state["answers"]["store_author_item"] == {"author": "User Author Two"}
    assert state["answers"]["store_title_item"] == {"title": "User Book Two"}
    assert state["vars"]["phase1"]["metadata"]["filename_policy"] == {
        "author": "User Author Two",
        "title": "User Book Two",
    }
    assert state["vars"]["phase1"]["metadata"]["values"] == {
        "album": "User Book Two",
        "album_artist": "User Author Two",
        "artist": "User Author Two",
        "title": "User Book Two",
    }


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
    _install_fast_phase1_validation(monkeypatch)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    if state["current_step_id"] == "select_authors":
        state = engine.submit_step(session_id, "select_authors", {"selection": "1"})
    state = engine.submit_step(session_id, "select_books", {"selection": "all"})
    state = engine.submit_step(session_id, "effective_author_item", {"value": "Canonical Author"})

    assert state["current_step_id"] == "effective_title_item"
    assert state["answers"]["store_author_item"] == {"author": "Canonical Author"}
    assert state["vars"]["phase1"]["metadata"]["book_title"] == "Book1"
    assert state["vars"]["phase1"]["select_books"]["selected_source_relative_paths"] == [
        "Author/Book1",
        "Author/Book2",
    ]


def test_select_authors_refreshes_filtered_book_defaults_for_two_pass_flow(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A", "Book1")
    _write_book(roots["inbox"], "A", "Book2")
    _write_book(roots["inbox"], "B", "Book3")

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    state = engine.submit_step(session_id, "select_authors", {"selection": "1"})
    state = engine.submit_step(session_id, "select_books", {"selection": "all"})

    assert state["current_step_id"] == "effective_author_item"
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

    assert repaired["vars"] == {}
    assert repaired["answers"]["select_authors"]["selection_expr"] == "all"
    assert repaired["answers"]["select_books"]["selection_expr"] == "all"


def test_default_v3_phase1_runtime_step_uses_flow_visible_runtime_projection() -> None:
    definition = build_default_wizard_definition_v3()
    phase1_node = next(
        node for node in definition["nodes"] if node["step_id"] == "phase1_runtime_defaults"
    )
    op = phase1_node["op"]

    assert op["primitive_id"] == "flow.invoke"
    assert op["primitive_version"] == 1
    assert op["inputs"]["target_library"] == "phase1_runtime_defaults_pipeline"
    assert op["inputs"]["target_subflow"] == "phase1_runtime_defaults_pipeline"
