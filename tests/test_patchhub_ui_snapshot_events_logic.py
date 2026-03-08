from __future__ import annotations

from pathlib import Path


def _read(rel: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / rel).read_text(encoding="utf-8")


def test_app_loads_snapshot_events_module() -> None:
    src = _read("scripts/patchhub/static/app.js")
    assert '"/static/app_part_snapshot_events.js"' in src


def test_snapshot_events_refresh_overview_once() -> None:
    src = _read("scripts/patchhub/static/app_part_snapshot_events.js")
    assert 'new EventSource("/api/events")' in src
    assert '__ph_w.refreshOverviewSnapshot({ mode: "latest" })' in src


def test_wire_init_uses_sse_before_idle_polling_fallback() -> None:
    src = _read("scripts/patchhub/static/app_part_wire_init.js")
    assert "__ph_w.ensureSnapshotEvents();" in src
    assert "__ph_w.snapshotEventsNeedPolling()" in src
