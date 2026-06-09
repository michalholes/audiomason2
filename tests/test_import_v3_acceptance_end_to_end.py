"""Issue 112: acceptance coverage for the default v3 CLI import path."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from audiomason.core.config import ConfigResolver

run_launcher = import_module("plugins.import.cli_renderer").run_launcher
ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine


def _make_engine(tmp_path: Path) -> tuple[Any, ConfigResolver, Path]:
    roots = {
        name: tmp_path / name for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards")
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    defaults = cast(
        dict[str, object],
        {
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
            "plugins": {
                "import": {
                    "cli": {
                        "launcher_mode": "fixed",
                        "default_root": "inbox",
                        "default_path": "src",
                        "noninteractive": False,
                        "render": {"confirm_defaults": True, "nav_ui": "prompt"},
                    }
                }
            },
        },
    )
    resolver = ConfigResolver(
        cli_args={},
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    return ImportWizardEngine(resolver=resolver), resolver, roots["wizards"]


def _write_source_tree(tmp_path: Path) -> None:
    book_dir = tmp_path / "inbox" / "src" / "Author A" / "Book A"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "track01.mp3").write_text("x", encoding="utf-8")


def _fast_validated_author_title(
    *,
    author: str,
    title: str,
) -> tuple[dict[str, object], dict[str, object]]:
    return (
        {
            "provider": "metadata_openlibrary",
            "author": {
                "valid": False,
                "canonical": None,
                "suggestion": author,
            },
            "book": {
                "valid": False,
                "canonical": None,
                "suggestion": {"author": author, "title": title},
            },
        },
        {
            "valid": False,
            "canonical": None,
            "suggestion": {"author": author, "title": title},
        },
    )


def test_default_v3_cli_acceptance_keeps_selection_and_plan_state(tmp_path: Path) -> None:
    _write_source_tree(tmp_path)
    engine, resolver, wizards_root = _make_engine(tmp_path)
    metadata_boundary = cast(Any, import_module("plugins.import.metadata_boundary"))

    original_validated = metadata_boundary.validate_author_title
    metadata_boundary.validate_author_title = cast(Any, _fast_validated_author_title)

    printed: list[str] = []

    def _input_fn(prompt: str) -> str:
        return "y" if "Start processing" in prompt else ""

    try:
        rc = run_launcher(
            engine=engine,
            resolver=resolver,
            cli_overrides={},
            input_fn=_input_fn,
            print_fn=printed.append,
        )
    finally:
        metadata_boundary.validate_author_title = original_validated

    assert rc == 0

    session_dirs = sorted((wizards_root / "import" / "sessions").iterdir())
    assert len(session_dirs) == 1
    session_dir = session_dirs[0]

    effective_model = json.loads((session_dir / "effective_model.json").read_text(encoding="utf-8"))
    state = json.loads((session_dir / "state.json").read_text(encoding="utf-8"))
    plan = json.loads((session_dir / "plan.json").read_text(encoding="utf-8"))
    job_requests = json.loads((session_dir / "job_requests.json").read_text(encoding="utf-8"))

    assert effective_model["flowmodel_kind"] == "dsl_step_graph_v3"
    assert state["phase"] == 2
    assert state["status"] == "processing"
    assert state["current_step_id"] == "processing"
    assert state["selected_author_ids"]
    assert state["selected_book_ids"]
    assert state["answers"]["final_summary_confirm"]["confirm_start"] is True
    assert state["computed"]["plan_summary"]["files"] == 0
    assert plan["summary"]["selected_books"] == 1
    assert state["vars"]["phase1"]["cover"]["mode"] == "per_book"
    assert state["vars"]["phase1"]["cover"]["allowed_modes"] == [
        "per_book",
        "skip",
        "url",
    ]
    assert state["vars"]["phase1"]["policy"]["delete_source_policy"]["clean_inbox"] == "ask"
    assert state["vars"]["phase1"]["metadata"]["filename_policy"] == {
        "author": "src",
        "title": "Author A",
    }
    assert state["vars"]["phase1"]["metadata"]["values"] == {
        "title": "Author A",
        "artist": "src",
        "album": "Author A",
        "album_artist": "src",
    }
    assert job_requests["actions"][0]["source"] == {
        "relative_path": "src/Author A",
        "root": "inbox",
    }
    assert job_requests["actions"][0]["authority"]["rename"] == {
        "mode": "explicit_relative_paths",
        "outputs": ["01.mp3"],
    }
    trace = [entry["step_id"] for entry in state["trace"]]
    assert trace[0] == "phase1_set_runtime_defaults"
    assert trace[-1] == "final_summary_confirm"
    for step_id in ["select_authors", "select_books", "effective_author_item"]:
        assert step_id in trace
    assert trace.index("select_authors") < trace.index("select_books")
    assert trace.index("select_books") < trace.index("effective_author_item")

    joined = "\n".join(printed)
    assert "Step: effective_author_item" in joined
    assert "Step: final_summary_confirm" in joined

    for hidden_step in [
        "filename_policy_author",
        "filename_policy_title",
        "id3_policy_title",
        "id3_policy_artist",
        "id3_policy_album",
        "id3_policy_album_artist",
        "parallelism",
    ]:
        assert f"Step: {hidden_step}" not in joined
    assert "Step: covers_policy_mode" in joined
    assert "Step: audio_processing_enabled" in joined
    assert "job_ids:" in joined
    assert '"batch_size": 1' in joined
