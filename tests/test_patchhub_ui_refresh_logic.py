from __future__ import annotations

from pathlib import Path


def _read(rel: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / rel).read_text(encoding="utf-8")


def test_idle_overview_refresh_uses_snapshot_endpoint() -> None:
    src = _read("scripts/patchhub/static/app_part_jobs.js")
    assert "function refreshOverviewSnapshot(opts)" in src
    assert 'apiGetETag("ui_snapshot", "/api/ui_snapshot" + qs' in src
    assert 'phCall("renderHeaderFromSummary", snap.header || {}, headerBaseLabel())' in src


def test_runs_refresh_uses_etag_single_flight_wrapper() -> None:
    src = _read("scripts/patchhub/static/app_part_runs.js")
    assert 'apiGetETag("runs_list", `/api/runs?${q.join("&")}`' in src
    assert 'single_flight: mode === "periodic"' in src


def test_wire_init_uses_snapshot_first_idle_flow() -> None:
    src = _read("scripts/patchhub/static/app_part_wire_init.js")
    assert 'phCall("refreshOverviewSnapshot", { mode: "user" })' in src
    assert 'phCall("refreshRuns", { mode: "user" });' in src
    assert 'phCall("refreshHeader", { mode: "user" });' in src


def test_hidden_active_keeps_active_orchestration_paths() -> None:
    wire_src = _read("scripts/patchhub/static/app_part_wire_init.js")
    assert "function hasTrackedActiveJob()" in wire_src
    assert "activeMode = hasTrackedActiveJob();" in wire_src
    assert "if (document.hidden && !activeMode) {" in wire_src
    assert "startTimers({ keepLiveStream: keepLiveStream });" in wire_src

    snapshot_src = _read("scripts/patchhub/static/app_part_snapshot_events.js")
    assert 'PH.call("hasTrackedActiveJob") || document.hidden' in snapshot_src


def test_live_progress_prefers_stream_with_tail_fallback() -> None:
    progress_src = _read("scripts/patchhub/static/patchhub_progress_ui.js")
    assert 'String(ev.event || "") === "stream_end"' in progress_src
    assert "function updateProgressPanelFromTailText(text, opts)" in progress_src

    runs_src = _read("scripts/patchhub/static/app_part_runs.js")
    assert 'phCall("updateProgressPanelFromTailText", t);' in runs_src
