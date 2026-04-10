"""Import plugin: diagnostics emission during finalize."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

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
    ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
else:  # pragma: no cover - isolated validator tree

    class _ImportWizardEngineStub:
        pass

    ImportWizardEngine = _ImportWizardEngineStub


@dataclass(frozen=True)
class _Job:
    job_id: str


class _Bus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def publish(self, event: str, payload: dict[str, object]) -> None:
        self.events.append((event, payload))


def _make_engine(tmp_path: Path) -> tuple[Any, dict[str, Path]]:
    if not _HAS_SRC_TREE:
        raise RuntimeError("src tree unavailable")
    config_resolver_cls = import_module("audiomason.core.config").ConfigResolver
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
    cli_args = defaults
    resolver = config_resolver_cls(
        cli_args=cli_args,
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    return ImportWizardEngine(resolver=resolver), roots


def _write_inbox_source_dir(roots: dict[str, Path], rel_dir: str) -> None:
    d = roots["inbox"] / rel_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "file.txt").write_text("x", encoding="utf-8")


def _mutate_state_for_finalize(roots: dict[str, Path], session_id: str) -> None:
    state_path = roots["wizards"] / "import" / "sessions" / session_id / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("answers", {})["final_summary_confirm"] = {"confirm_start": True}
    state.setdefault("conflicts", {})["policy"] = "ask"
    state["status"] = "in_progress"
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _event_data(payload: dict[str, object]) -> dict[str, object]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def test_emits_finalize_request_and_job_create(monkeypatch, tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    rel = "book7"
    _write_inbox_source_dir(roots, rel)

    state = engine.create_session("inbox", rel, mode="stage")
    session_id = str(state.get("session_id") or "")
    assert session_id
    _mutate_state_for_finalize(roots, session_id)

    bus = _Bus()
    engine_mod = import_module("plugins.import.engine")
    monkeypatch.setattr(engine_mod, "get_event_bus", lambda: bus)

    from audiomason.core.jobs import api as jobs_api

    def _create_job(self, job_type, *, meta):
        return _Job(job_id="job-789")

    monkeypatch.setattr(jobs_api.JobService, "create_job", _create_job)
    diag_mod = import_module("plugins.import.engine_diagnostics_required")
    monkeypatch.setattr(diag_mod, "submit_process_job", lambda **_kw: None)

    out = engine.start_processing(session_id, {"confirm": True})
    assert out == {"job_ids": ["job-789"], "batch_size": 0}

    names = [e for (e, _p) in bus.events]
    assert "finalize.request" in names
    assert "job.create" in names

    req_payload = next(p for (e, p) in bus.events if e == "finalize.request")
    job_payload = next(p for (e, p) in bus.events if e == "job.create")

    req_data = _event_data(req_payload)
    job_data = _event_data(job_payload)

    for data in (req_data, job_data):
        assert data.get("session_id") == session_id
        assert str(data.get("model_fingerprint") or "")
        assert str(data.get("discovery_fingerprint") or "")
        assert str(data.get("effective_config_fingerprint") or "")


def test_submit_process_job_uses_session_engine_outside_repo_cwd(
    monkeypatch, tmp_path: Path
) -> None:
    diag_mod = import_module("plugins.import.engine_diagnostics_required")
    engine, roots = _make_engine(tmp_path)

    from audiomason.core.orchestration import Orchestrator

    seen: dict[str, object] = {}

    def _submit(self, job_id: str, *, verbosity: int = 1) -> None:
        seen["job_id"] = job_id
        seen["verbosity"] = verbosity
        seen["jobs_root"] = self._jobs.store.root

    monkeypatch.setattr(Orchestrator, "submit_process_contract_job", _submit)

    old_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        diag_mod.submit_process_job(engine=engine, job_id="job-ctx", verbosity=3)
    finally:
        os.chdir(old_cwd)

    assert seen["job_id"] == "job-ctx"
    assert seen["verbosity"] == 3
    assert Path(cast(str, seen["jobs_root"])) == roots["jobs"]


def test_failure_does_not_emit_job_create(monkeypatch, tmp_path: Path) -> None:
    engine, roots = _make_engine(tmp_path)
    rel = "book8"
    _write_inbox_source_dir(roots, rel)

    state = engine.create_session("inbox", rel, mode="stage")
    session_id = str(state.get("session_id") or "")
    assert session_id
    _mutate_state_for_finalize(roots, session_id)

    # Create a conflict so finalize fails.
    conflict_dir = roots["stage"] / rel
    conflict_dir.mkdir(parents=True, exist_ok=True)

    bus = _Bus()
    engine_mod = import_module("plugins.import.engine")
    monkeypatch.setattr(engine_mod, "get_event_bus", lambda: bus)

    out = engine.start_processing(session_id, {"confirm": True})
    assert out.get("error", {}).get("code") == "CONFLICTS_UNRESOLVED"

    names = [e for (e, _p) in bus.events]
    assert "finalize.request" in names
    assert "job.create" not in names


def _write_minimal_plugin(
    repo_root: Path,
    *,
    name: str,
    class_name: str,
    dir_name: str | None = None,
) -> None:
    plugins_root = repo_root / "plugins"
    plugins_root.mkdir(parents=True, exist_ok=True)
    (plugins_root / "__init__.py").write_text("", encoding="utf-8")
    plugin_dir = plugins_root / str(dir_name or name)
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.py").write_text(
        f"class {class_name}:\n    pass\n",
        encoding="utf-8",
    )
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                f"name: {name}",
                'version: "1.0.0"',
                "description: test plugin",
                "author: tests",
                "license: MIT",
                f"entrypoint: plugin:{class_name}",
                "interfaces: []",
                "hooks: []",
                "dependencies: {}",
                "config_schema: {}",
                "test_level: none",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_submit_loader_autoloads_required_process_plugins(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    for name, class_name, dir_name in [
        ("audio_processor", "AudioProcessorPlugin", "zz-audio-provider"),
        ("cover_handler", "CoverHandlerPlugin", "aa-cover-provider"),
        ("id3_tagger", "ID3TaggerPlugin", "mm-id3-provider"),
    ]:
        _write_minimal_plugin(
            repo_root,
            name=name,
            class_name=class_name,
            dir_name=dir_name,
        )

    diag_mod = import_module("plugins.import.engine_diagnostics_required")

    def _resolve_import_plugin(*, plugin_name: str):
        package = __import__(f"plugins.{plugin_name}.plugin", fromlist=[plugin_name])
        class_name = {
            "audio_processor": "AudioProcessorPlugin",
            "cover_handler": "CoverHandlerPlugin",
            "id3_tagger": "ID3TaggerPlugin",
        }[plugin_name]
        return getattr(package, class_name)()

    monkeypatch.syspath_prepend(str(repo_root))
    monkeypatch.setattr(diag_mod, "resolve_import_plugin", _resolve_import_plugin)

    loader = diag_mod._plugin_loader(engine=object())
    diag_mod._ensure_required_process_plugins(loader=loader)

    assert loader.list_plugins() == [
        "import",
        "audio_processor",
        "cover_handler",
        "id3_tagger",
    ]


def test_engine_diagnostics_required_source_has_no_local_root_or_discovery_bootstrap() -> None:
    source = Path("plugins/import/engine_diagnostics_required.py").read_text(encoding="utf-8")

    assert "from audiomason.core.loader import PluginLoader" not in source
    assert "_builtin_plugins_root" not in source
    assert "_user_plugins_root" not in source
    assert "_resolve_plugin_via_loader" not in source
    assert "_ContractPluginLoader" in source
    assert "resolve_import_plugin(plugin_name=plugin_name)" in source
