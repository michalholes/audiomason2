from __future__ import annotations

from pathlib import Path


def _read(rel: str) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / rel).read_text(encoding="utf-8")


def test_snapshot_events_requests_delta_endpoint() -> None:
    src = _read("scripts/patchhub/static/app_part_snapshot_events.js")
    assert '"/api/ui_snapshot_delta?since_seq="' in src


def test_snapshot_events_falls_back_to_full_snapshot_refresh() -> None:
    src = _read("scripts/patchhub/static/app_part_snapshot_events.js")
    assert "resync_needed" in src
    assert '__ph_w.refreshOverviewSnapshot({ mode: "latest" })' in src


def test_snapshot_events_applies_removed_delta_items() -> None:
    src = _read("scripts/patchhub/static/app_part_snapshot_events.js")
    assert "(delta.removed || []).forEach" in src
    assert "overviewWorkspaceKey" in src
