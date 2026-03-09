from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_ui_contains_zip_subset_and_progress_applied_hooks() -> None:
    html = (REPO_ROOT / "scripts" / "patchhub" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    assert 'id="zipSubsetStrip"' in html
    assert 'id="zipSubsetModal"' in html
    assert 'id="progressApplied"' in html


def test_app_boot_sequence_loads_zip_subset_module() -> None:
    app_js = (REPO_ROOT / "scripts" / "patchhub" / "static" / "app.js").read_text(encoding="utf-8")
    assert "/static/app_part_zip_subset.js" in app_js
