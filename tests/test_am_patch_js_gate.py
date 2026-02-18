from __future__ import annotations

import sys
from pathlib import Path


def _import_gate():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.gates import check_js_gate

    return check_js_gate


def test_js_gate_not_triggered_when_no_js_touched() -> None:
    check_js_gate = _import_gate()
    triggered, js_paths = check_js_gate(
        ["src/a.py", "docs/specification.md"],
        extensions=[".js"],
    )
    assert triggered is False
    assert js_paths == []


def test_js_gate_triggers_and_sorts_paths() -> None:
    check_js_gate = _import_gate()
    triggered, js_paths = check_js_gate(
        ["b.js", "a.js", "src/x.py", "plugins/p.mjs"],
        extensions=[".js", ".mjs"],
    )
    assert triggered is True
    assert js_paths == ["a.js", "b.js", "plugins/p.mjs"]


def test_js_gate_respects_extensions_filter() -> None:
    check_js_gate = _import_gate()
    triggered, js_paths = check_js_gate(
        ["a.mjs", "b.js"],
        extensions=[".js"],
    )
    assert triggered is True
    assert js_paths == ["b.js"]


def test_js_gate_handles_extension_without_dot() -> None:
    check_js_gate = _import_gate()
    triggered, js_paths = check_js_gate(
        ["a.JS", "b.txt"],
        extensions=["js"],
    )
    assert triggered is True
    assert js_paths == ["a.JS"]
