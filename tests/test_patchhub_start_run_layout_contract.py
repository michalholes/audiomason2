from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_start_run_layout_contract_matches_compact_layout() -> None:
    html = (REPO_ROOT / "scripts" / "patchhub" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    css = (REPO_ROOT / "scripts" / "patchhub" / "static" / "app.css").read_text(encoding="utf-8")
    assert "B) Start run" not in html
    assert 'id="mode" class="input start-run-mode"' in html
    assert 'id="patchPath"' in html
    assert 'class="input start-run-patch"' in html
    assert 'id="browsePatch" class="btn btn-small hidden"' in html
    assert 'id="issueId"' in html
    assert 'class="input start-run-issue"' in html
    assert 'id="liveAutoscrollToggle"' in html
    assert "Auto-scroll" in html
    assert ".start-run-mode" in css
    assert ".start-run-issue" in css
    assert "flex: 0 0 50px;" in css
    assert "width: 50px;" in css
    assert ".start-run-patch" in css
    assert "flex: 0 0 120px;" in css
    assert "width: 120px;" in css
