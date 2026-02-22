"""Import CLI nav_ui=inline behavior."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

run_launcher = import_module("plugins.import.cli_renderer").run_launcher
ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine


def _make_engine(tmp_path: Path, *, nav_ui: str) -> tuple[ImportWizardEngine, ConfigResolver]:
    roots = {
        "inbox": tmp_path / "inbox",
        "stage": tmp_path / "stage",
        "outbox": tmp_path / "outbox",
        "jobs": tmp_path / "jobs",
        "config": tmp_path / "config",
        "wizards": tmp_path / "wizards",
    }
    for p in roots.values():
        p.mkdir(parents=True, exist_ok=True)

    # Provide a minimal directory structure so the first wizard step has selectable items.
    (roots["inbox"] / "Book1").mkdir(parents=True, exist_ok=True)

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
                    "launcher_mode": "fixed",
                    "default_root": "inbox",
                    "default_path": "",
                    "noninteractive": False,
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
    return ImportWizardEngine(resolver=resolver), resolver


def test_nav_ui_inline_does_not_prompt_for_action(tmp_path: Path) -> None:
    engine, resolver = _make_engine(tmp_path, nav_ui="inline")

    inputs = iter(["all", ":cancel"])

    def _input(prompt: str) -> str:
        if "Action (:next" in prompt:
            raise AssertionError("Action prompt must not be shown for nav_ui=inline")
        return next(inputs)

    printed: list[str] = []

    rc = run_launcher(
        engine=engine,
        resolver=resolver,
        cli_overrides={},
        input_fn=_input,
        print_fn=printed.append,
    )

    assert rc == 1


def test_nav_ui_inline_accepts_cancel_inline(tmp_path: Path) -> None:
    engine, resolver = _make_engine(tmp_path, nav_ui="inline")

    def _input(prompt: str) -> str:
        if "Action (:next" in prompt:
            raise AssertionError("Action prompt must not be shown for nav_ui=inline")
        return ":cancel"

    printed: list[str] = []

    rc = run_launcher(
        engine=engine,
        resolver=resolver,
        cli_overrides={},
        input_fn=_input,
        print_fn=printed.append,
    )

    assert rc == 1
