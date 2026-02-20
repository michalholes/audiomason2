"""Anti-drift checks for catalog ordering and renderer neutrality."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
RootName = import_module("plugins.file_io.service").RootName
ensure_default_models = import_module("plugins.import.defaults").ensure_default_models
read_json = import_module("plugins.import.storage").read_json


def _make_engine(tmp_path: Path) -> ImportWizardEngine:
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
    return ImportWizardEngine(resolver=resolver)


def test_default_catalog_step_ids_and_order(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()
    ensure_default_models(fs)

    catalog = read_json(fs, RootName.WIZARDS, "import/catalog/catalog.json")
    assert isinstance(catalog, dict)
    steps_any = catalog.get("steps")
    assert isinstance(steps_any, list)
    steps = [s for s in steps_any if isinstance(s, dict)]

    expected = [
        "select_authors",
        "select_books",
        "plan_preview_batch",
        "effective_author_title",
        "filename_policy",
        "covers_policy",
        "id3_policy",
        "audio_processing",
        "publish_policy",
        "delete_source_policy",
        "conflict_policy",
        "parallelism",
        "final_summary_confirm",
        "resolve_conflicts_batch",
        "processing",
    ]

    got = [str(s.get("step_id")) for s in steps]
    assert got == expected

    computed = {str(s.get("step_id")): bool(s.get("computed_only")) for s in steps}
    assert computed["plan_preview_batch"] is True
    assert computed["processing"] is True


def test_renderer_neutrality_no_step_id_branching() -> None:
    # Renderer layers must not branch on step_id values.
    # We enforce this by forbidding step_id literal comparisons.
    repo_root = Path(__file__).resolve().parents[2]
    cli_text = (repo_root / "plugins" / "import" / "cli_renderer.py").read_text(encoding="utf-8")
    ui_text = (repo_root / "plugins" / "import" / "ui_api.py").read_text(encoding="utf-8")

    forbidden = [
        "step_id == ",
        'get("step_id") == ',
        "get('step_id') == ",
    ]

    for f in forbidden:
        assert f not in cli_text
        assert f not in ui_text
