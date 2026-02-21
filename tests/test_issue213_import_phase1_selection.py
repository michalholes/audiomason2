from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
RootName = import_module("plugins.file_io.service").RootName
ensure_default_models = import_module("plugins.import.defaults").ensure_default_models
read_json = import_module("plugins.import.storage").read_json


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
    # Author A / Book 1
    d = roots["inbox"] / "A" / "Book1"
    d.mkdir(parents=True, exist_ok=True)
    (d / "a.txt").write_text("x", encoding="utf-8")

    # Author A / Book 2
    d = roots["inbox"] / "A" / "Book2"
    d.mkdir(parents=True, exist_ok=True)
    (d / "b.txt").write_text("y", encoding="utf-8")

    # Author B / Book 3
    d = roots["inbox"] / "B" / "Book3"
    d.mkdir(parents=True, exist_ok=True)
    (d / "c.txt").write_text("z", encoding="utf-8")

    # Unicode author/title (diacritics), encoded as escapes to keep repo ASCII-only.
    author = "Meyr\u00ednk, Gust\u00e1v"
    book = "Obrazy vep\u00edsan\u00e9 do vzduchu"
    d = roots["inbox"] / author / book
    d.mkdir(parents=True, exist_ok=True)
    (d / "u.txt").write_text("u", encoding="utf-8")


def test_effective_model_contains_selection_items(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    fs = engine.get_file_service()

    _write_inbox_tree(roots)
    ensure_default_models(fs)

    state = engine.create_session("inbox", "", mode="stage")
    assert "error" not in state
    session_id = str(state["session_id"])

    em = read_json(fs, RootName.WIZARDS, f"import/sessions/{session_id}/effective_model.json")
    assert isinstance(em, dict)

    steps = em.get("steps")
    assert isinstance(steps, list)

    by_id = {s.get("step_id"): s for s in steps if isinstance(s, dict)}
    found_non_ascii_display = False
    for sid, prefix in [("select_authors", "author:"), ("select_books", "book:")]:
        step = by_id.get(sid)
        assert isinstance(step, dict)
        fields = step.get("fields")
        assert isinstance(fields, list)
        ms = [f for f in fields if isinstance(f, dict) and f.get("type") == "multi_select_indexed"]
        assert len(ms) >= 1
        items = ms[0].get("items")
        assert isinstance(items, list)
        assert items
        for it in items:
            assert isinstance(it, dict)
            item_id = it.get("item_id")
            label = it.get("label")
            display_label = it.get("display_label")
            assert isinstance(item_id, str) and item_id.startswith(prefix)
            assert isinstance(label, str)
            assert isinstance(display_label, str)
            if not display_label.isascii():
                found_non_ascii_display = True
            assert label.isascii()

    assert found_non_ascii_display


def test_out_of_range_selection_is_validation_error(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    fs = engine.get_file_service()

    _write_inbox_tree(roots)
    ensure_default_models(fs)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])

    res = engine.submit_step(session_id, "select_authors", {"selection_expr": "999"})
    err = res.get("error") if isinstance(res, dict) else None
    assert isinstance(err, dict)
    assert err.get("code") == "VALIDATION_ERROR"


def test_cli_renderer_has_no_step_id_branching() -> None:
    p = Path(__file__).resolve().parents[1] / "plugins" / "import" / "cli_renderer.py"
    txt = p.read_text(encoding="utf-8")
    assert "if step_id ==" not in txt
