from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_gate_options_controls_are_present_on_main_screen() -> None:
    html = _read("scripts/patchhub/templates/index.html")
    assert 'id="gateOptionsBtn"' in html
    assert 'id="gateOptionsModal"' in html
    assert 'id="liveCopySelection"' in html
    assert 'id="liveCopyAll"' in html


def test_gate_options_module_is_loaded_and_registered() -> None:
    app_src = _read("scripts/patchhub/static/app.js")
    mod_src = _read("scripts/patchhub/static/app_part_gate_options.js")
    css_src = _read("scripts/patchhub/static/app.css")
    assert "/static/app_part_gate_options.js" in app_src
    assert 'PH.register("app_part_gate_options"' in mod_src
    assert "clearGateOverrides" in mod_src
    assert "getGateOptionsEnqueuePayload" in mod_src
    assert "gate-options-switch" in mod_src
    assert ".gate-options-switch" in css_src
    assert ".gate-options-passive" in css_src


def test_wire_init_dispatches_gate_modal_and_live_copy_setup() -> None:
    wire_src = _read("scripts/patchhub/static/app_part_wire_init.js")
    assert 'phCall("initGateOptionsUi")' in wire_src
    assert 'phCall("initLiveCopyButtons")' in wire_src
