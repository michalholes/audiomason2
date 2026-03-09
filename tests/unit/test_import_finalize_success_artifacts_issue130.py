from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus

ImportPlugin = import_module("plugins.import.plugin").ImportPlugin
processed_required = import_module("plugins.import.processed_registry_required")
read_json = import_module("plugins.import.storage").read_json
RootName = import_module("plugins.file_io.service").RootName


def _make_plugin(tmp_path: Path) -> tuple[object, dict[str, Path]]:
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
    return ImportPlugin(resolver=resolver), roots


def _disable_optional_steps() -> dict[str, object]:
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


def _write_inbox_books(roots: dict[str, Path]) -> None:
    for book in ("Book1", "Book2"):
        book_dir = roots["inbox"] / "AuthorA" / book
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / "track.txt").write_text(book, encoding="utf-8")


def _mutate_state_for_finalize(roots: dict[str, Path], session_id: str, *, policy: str) -> None:
    state_path = roots["wizards"] / "import" / "sessions" / session_id / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("inputs", {})["final_summary_confirm"] = {"confirm_start": True}
    state.setdefault("conflicts", {})["policy"] = policy
    state["status"] = "in_progress"
    state_path.write_text(json.dumps(state), encoding="utf-8")


def _start_processing(plugin: object, roots: dict[str, Path]) -> tuple[str, str]:
    engine = plugin.get_engine()
    _write_inbox_books(roots)
    state = engine.create_session(
        "inbox",
        "",
        mode="stage",
        flow_overrides=_disable_optional_steps(),
    )
    session_id = str(state.get("session_id") or "")
    assert session_id
    step1 = engine.submit_step(session_id, "select_authors", {"selection_expr": "all"})
    assert "error" not in step1
    step2 = engine.submit_step(session_id, "select_books", {"selection_expr": "all"})
    assert "error" not in step2
    _ = engine.compute_plan(session_id)
    _mutate_state_for_finalize(roots, session_id, policy="auto")
    started = engine.start_processing(session_id, {"confirm": True})
    job_ids = started.get("job_ids")
    assert isinstance(job_ids, list) and len(job_ids) == 1
    return session_id, str(job_ids[0])


def test_finalize_success_artifacts_and_ignore_registry_are_success_only(tmp_path: Path) -> None:
    processed_required._INSTALLED = False
    bus = get_event_bus()
    bus.clear()

    plugin, roots = _make_plugin(tmp_path)
    session_id, job_id = _start_processing(plugin, roots)
    fs = plugin.get_engine().get_file_service()

    report_rel = f"import/sessions/{session_id}/finalize/report.json"
    summary_rel = f"import/sessions/{session_id}/finalize/dry_run_summary.json"
    log_rel = f"import/sessions/{session_id}/finalize/processing_log.jsonl"
    ignore_rel = "import/processed/ignore_registry.json"

    bus.publish(
        "diag.job.end",
        build_envelope(
            event="diag.job.end",
            component="jobs",
            operation="run_job",
            data={
                "job_id": job_id,
                "job_type": "process",
                "status": "failed",
                "duration_ms": 1,
            },
        ),
    )

    assert not fs.exists(RootName.WIZARDS, report_rel)
    assert not fs.exists(RootName.WIZARDS, summary_rel)
    assert not fs.exists(RootName.WIZARDS, log_rel)
    assert not fs.exists(RootName.WIZARDS, ignore_rel)

    bus.publish(
        "diag.job.end",
        build_envelope(
            event="diag.job.end",
            component="jobs",
            operation="run_job",
            data={
                "job_id": job_id,
                "job_type": "process",
                "status": "succeeded",
                "duration_ms": 1,
            },
        ),
    )

    report = read_json(fs, RootName.WIZARDS, report_rel)
    summary = read_json(fs, RootName.WIZARDS, summary_rel)
    ignore_registry = read_json(fs, RootName.WIZARDS, ignore_rel)
    state = read_json(fs, RootName.WIZARDS, f"import/sessions/{session_id}/state.json")

    assert report["status"] == "succeeded"
    assert report["artifacts"]["dry_run_summary"] == f"wizards:{summary_rel}"
    assert report["artifacts"]["processing_log"] == f"wizards:{log_rel}"

    assert summary["counts"] == {"books": 2, "capabilities": 6}
    assert [book["source"]["relative_path"] for book in summary["books"]] == [
        "AuthorA/Book1",
        "AuthorA/Book2",
    ]
    assert [cap["kind"] for cap in summary["books"][0]["capabilities"]] == [
        "audio.import",
        "metadata.tags",
        "publish.write",
    ]

    log_lines = (roots["wizards"] / log_rel).read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == 2
    line0 = json.loads(log_lines[0])
    assert line0["status"] == "succeeded"
    assert line0["source"] == {"root": "inbox", "relative_path": "AuthorA/Book1"}

    assert ignore_registry == {
        "schema_version": 1,
        "sources": [
            {"relative_path": "AuthorA/Book1", "root": "inbox"},
            {"relative_path": "AuthorA/Book2", "root": "inbox"},
        ],
    }

    finalize = state.get("computed", {}).get("finalize")
    assert finalize == {
        "dry_run_summary_path": f"wizards:{summary_rel}",
        "job_id": job_id,
        "processing_log_path": f"wizards:{log_rel}",
        "report_path": f"wizards:{report_rel}",
        "status": "succeeded",
    }
    assert state["status"] == "succeeded"
