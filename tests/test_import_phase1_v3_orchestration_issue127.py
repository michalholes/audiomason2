from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
RootName = import_module("plugins.file_io.service.types").RootName
WIZARD_DEFINITION_REL_PATH = import_module(
    "plugins.import.wizard_definition_model"
).WIZARD_DEFINITION_REL_PATH
build_default_wizard_definition_v3 = import_module(
    "plugins.import.dsl.default_wizard_v3"
).build_default_wizard_definition_v3


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

    assert state["current_step_id"] == "effective_author_title"
    assert state["answers"]["select_authors"]["selection_expr"] == "1"
    assert state["answers"]["select_books"]["selection_expr"] == "1"
    assert state["vars"]["phase1"]["metadata"]["values"] == {
        "title": "Book",
        "artist": "Author",
        "album": "Book",
        "album_artist": "Author",
    }
    assert state["vars"]["phase1"]["cover"]["mode"] == "embedded"
    assert state["vars"]["phase1"]["runtime"]["effective_author_title"] == {
        "author": "Author",
        "title": "Book",
    }
    assert state["vars"]["phase1"]["policy"]["publish_policy"] == {"target_root": "stage"}


def test_select_authors_refreshes_filtered_book_defaults_for_two_pass_flow(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_book(roots["inbox"], "A", "Book1")
    _write_book(roots["inbox"], "A", "Book2")
    _write_book(roots["inbox"], "B", "Book3")

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    state = engine.submit_step(session_id, "select_authors", {"selection": "1"})

    assert state["current_step_id"] == "select_books"
    assert state["vars"]["phase1"]["select_books"]["selection_expr"] == "1,2"
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
