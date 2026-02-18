"""Import wizard: spec alignment regression tests.

These tests validate alignment with docs/specification.md section 10.
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine


def _make_engine(tmp_path: Path) -> tuple[ImportWizardEngine, dict[str, Path]]:
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


def _write_inbox_source_dir(roots: dict[str, Path], rel_dir: str) -> None:
    d = roots["inbox"] / rel_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "file.txt").write_text("x", encoding="utf-8")


def _disable_optional_steps(roots: dict[str, Path]) -> None:
    cfg_path = roots["wizards"] / "import" / "config" / "flow_config.json"
    cfg_any = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg_any["steps"] = {
        "filename_policy": {"enabled": False},
        "covers_policy": {"enabled": False},
        "id3_policy": {"enabled": False},
        "audio_processing": {"enabled": False},
        "publish_policy": {"enabled": False},
        "delete_source_policy": {"enabled": False},
        "parallelism": {"enabled": False},
    }
    cfg_path.write_text(json.dumps(cfg_any), encoding="utf-8")


def _optional_disable_overrides() -> dict[str, object]:
    return {
        "steps": {
            "filename_policy": {"enabled": False},
            "covers_policy": {"enabled": False},
            "id3_policy": {"enabled": False},
            "audio_processing": {"enabled": False},
            "publish_policy": {"enabled": False},
            "delete_source_policy": {"enabled": False},
            "parallelism": {"enabled": False},
        }
    }


def test_flow_model_contains_resolve_conflicts_before_processing(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_inbox_source_dir(roots, "book1")

    flow_model = engine.get_flow_model()
    step_ids = [s.get("step_id") for s in flow_model.get("steps", [])]

    assert step_ids.count("resolve_conflicts_batch") == 1
    assert step_ids.count("processing") == 1
    assert step_ids.index("resolve_conflicts_batch") < step_ids.index("processing")


def test_step_schemas_match_spec_field_names(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_inbox_source_dir(roots, "book1")

    flow_model = engine.get_flow_model()
    steps = {s.get("step_id"): s for s in flow_model.get("steps", []) if isinstance(s, dict)}

    final_fields = [f.get("name") for f in steps["final_summary_confirm"].get("fields", [])]
    assert "confirm_start" in final_fields
    assert "confirm" not in final_fields

    resolve_fields = [f.get("name") for f in steps["resolve_conflicts_batch"].get("fields", [])]
    assert resolve_fields == ["confirm"]


def test_select_books_ok_auto_advances_past_plan_preview(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_inbox_source_dir(roots, "book1")

    state = engine.create_session(
        "inbox",
        "book1",
        mode="stage",
        flow_overrides=_optional_disable_overrides(),
    )
    session_id = str(state.get("session_id") or "")
    assert session_id

    state = engine.submit_step(session_id, "select_authors", {"selection_expr": "1"})
    assert state.get("current_step_id") == "select_books"

    state = engine.submit_step(session_id, "select_books", {"selection_expr": "1"})
    assert state.get("current_step_id") == "effective_author_title"


def test_final_summary_confirm_uses_confirm_start_gate(tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    _write_inbox_source_dir(roots, "book1")

    state = engine.create_session(
        "inbox",
        "book1",
        mode="stage",
        flow_overrides=_optional_disable_overrides(),
    )
    session_id = str(state.get("session_id") or "")
    assert session_id

    state = engine.submit_step(session_id, "select_authors", {"selection_expr": "1"})
    state = engine.submit_step(session_id, "select_books", {"selection_expr": "1"})
    assert state.get("current_step_id") == "effective_author_title"

    state = engine.submit_step(session_id, "effective_author_title", {"mode": "x"})
    assert state.get("current_step_id") == "conflict_policy"

    state = engine.submit_step(session_id, "conflict_policy", {"mode": "overwrite"})
    assert state.get("current_step_id") == "final_summary_confirm"

    state = engine.submit_step(session_id, "final_summary_confirm", {"confirm_start": False})
    assert state.get("current_step_id") == "final_summary_confirm"

    state = engine.submit_step(session_id, "final_summary_confirm", {"confirm_start": True})
    assert state.get("current_step_id") == "processing"
