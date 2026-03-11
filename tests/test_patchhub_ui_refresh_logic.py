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
