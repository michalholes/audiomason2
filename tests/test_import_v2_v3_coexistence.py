"""Issue 113: deterministic v2/v3 coexistence with the v3 default bootstrap."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
CANONICAL_STEP_ORDER = import_module("plugins.import.flow_runtime").CANONICAL_STEP_ORDER
RootName = import_module("plugins.file_io.service.types").RootName
WIZARD_DEFINITION_REL_PATH = import_module(
    "plugins.import.wizard_definition_model"
).WIZARD_DEFINITION_REL_PATH


def _make_engine(
    tmp_path: Path,
    *,
    launcher_mode: str = "fixed",
    noninteractive: bool = False,
    nav_ui: str = "prompt",
) -> tuple[ImportWizardEngine, dict[str, Path]]:
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
        "plugins": {
            "import": {
                "cli": {
                    "launcher_mode": launcher_mode,
                    "default_root": "inbox",
                    "default_path": "",
                    "noninteractive": noninteractive,
                    "render": {"nav_ui": nav_ui},
                }
            }
        },
    }
    resolver = ConfigResolver(
        cli_args={},
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    return ImportWizardEngine(resolver=resolver), roots


def _write_source_tree(roots: dict[str, Path]) -> None:
    book_dir = roots["inbox"] / "src" / "Author A" / "Book A"
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "track01.mp3").write_text("x", encoding="utf-8")


def _v2_definition() -> dict[str, object]:
    return {
        "version": 2,
        "graph": {
            "entry_step_id": CANONICAL_STEP_ORDER[0],
            "nodes": [{"step_id": step_id} for step_id in CANONICAL_STEP_ORDER],
            "edges": [
                {
                    "from_step_id": CANONICAL_STEP_ORDER[index],
                    "to_step_id": CANONICAL_STEP_ORDER[index + 1],
                    "priority": 0,
                    "when": None,
                }
                for index in range(len(CANONICAL_STEP_ORDER) - 1)
            ],
        },
    }


def test_v2_and_v3_sessions_can_coexist_deterministically(tmp_path: Path) -> None:
    engine, roots = _make_engine(
        tmp_path,
        launcher_mode="disabled",
        noninteractive=True,
        nav_ui="both",
    )
    _write_source_tree(roots)

    state_v3 = engine.create_session("inbox", "src")
    assert state_v3["session_id"]
    assert state_v3["current_step_id"] == "select_authors"

    state_v3_loaded = engine.get_state(str(state_v3["session_id"]))
    assert state_v3_loaded["effective_model"]["flowmodel_kind"] == "dsl_step_graph_v3"

    fs = engine.get_file_service()
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, _v2_definition())

    state_v2 = engine.create_session("inbox", "src")
    assert state_v2["session_id"] != state_v3["session_id"]
    assert state_v2["current_step_id"] == "select_authors"

    state_v2_loaded = engine.get_state(str(state_v2["session_id"]))
    assert state_v2_loaded["effective_model"].get("flowmodel_kind") != "dsl_step_graph_v3"

    state_v3_reloaded = engine.get_state(str(state_v3["session_id"]))
    assert state_v3_reloaded["effective_model"]["flowmodel_kind"] == "dsl_step_graph_v3"
