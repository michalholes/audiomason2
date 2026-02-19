from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
RootName = import_module("plugins.file_io.service").RootName
ensure_default_models = import_module("plugins.import.defaults").ensure_default_models
read_json = import_module("plugins.import.storage").read_json
atomic_write_json = import_module("plugins.import.storage").atomic_write_json


def _make_engine(tmp_path: Path):
    roots = {
        "inbox": tmp_path / "inbox",
        "stage": tmp_path / "stage",
        "outbox": tmp_path / "outbox",
        "jobs": tmp_path / "jobs",
        "config": tmp_path / "config",
        "wizards": tmp_path / "wizards",
    }
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
    return ImportWizardEngine(resolver=resolver), roots


def _write_inbox_tree(roots: dict[str, Path]) -> None:
    d = roots["inbox"] / "A" / "Book1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "a.txt").write_text("x", encoding="utf-8")

    d = roots["inbox"] / "B" / "Book2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "b.txt").write_text("y", encoding="utf-8")


def test_plan_json_contains_selected_books(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    fs = engine.get_file_service()

    _write_inbox_tree(roots)
    ensure_default_models(fs)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])

    engine.submit_step(session_id, "select_authors", {"selection_expr": "all"})
    engine.submit_step(session_id, "select_books", {"selection_expr": "1"})

    plan = engine.compute_plan(session_id)
    assert isinstance(plan, dict)
    selected = plan.get("selected_books")
    assert isinstance(selected, list)
    assert len(selected) == 1
    assert selected[0].get("book_id", "").startswith("book:")

    stored = read_json(fs, RootName.WIZARDS, f"import/sessions/{session_id}/plan.json")
    assert stored == plan


def test_invalid_selection_bounces_back_to_select_books(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    fs = engine.get_file_service()

    _write_inbox_tree(roots)
    ensure_default_models(fs)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])

    engine.submit_step(session_id, "select_authors", {"selection_expr": "all"})
    # NOTE: submit_step auto-advances through computed-only steps, so this will
    # compute the plan once already.
    state_after_books = engine.submit_step(session_id, "select_books", {"selection_expr": "1"})
    assert "error" not in state_after_books

    session_dir = f"import/sessions/{session_id}"
    discovery = read_json(fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
    assert isinstance(discovery, list)

    # Remove all entries for the selected book (A/Book1) to simulate inconsistency.
    new_discovery = []
    for it in discovery:
        rel = it.get("relative_path") if isinstance(it, dict) else None
        if isinstance(rel, str) and (rel == "A/Book1" or rel.startswith("A/Book1/")):
            continue
        new_discovery.append(it)

    atomic_write_json(fs, RootName.WIZARDS, f"{session_dir}/discovery.json", new_discovery)

    # Move back to select_books, then next must fail deterministically and return
    # to select_books.
    state_back = engine.apply_action(session_id, "back")
    assert "error" not in state_back
    if str(state_back.get("current_step_id") or "") != "select_books":
        state_back = engine.apply_action(session_id, "back")
        assert "error" not in state_back
    assert str(state_back.get("current_step_id") or "") == "select_books"

    state2 = engine.apply_action(session_id, "next")
    assert "error" not in state2
    assert str(state2.get("current_step_id") or "") == "select_books"
