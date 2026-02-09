from __future__ import annotations

import sys
from pathlib import Path


def _import_gate():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.gates import check_docs_gate

    return check_docs_gate


def test_docs_gate_not_triggered_when_no_watched_changes() -> None:
    check_docs_gate = _import_gate()
    ok, missing, trigger = check_docs_gate(
        ["patches/x.txt", "badguys/y.txt"],
        include=["src", "plugins"],
        exclude=["badguys", "patches"],
        required_files=["docs/changes.md", "docs/specification.md"],
    )
    assert ok is True
    assert missing == []
    assert trigger is None


def test_docs_gate_fails_when_triggered_and_docs_missing() -> None:
    check_docs_gate = _import_gate()
    ok, missing, trigger = check_docs_gate(
        ["src/a.py"],
        include=["src", "plugins"],
        exclude=["badguys", "patches"],
        required_files=["docs/changes.md", "docs/specification.md"],
    )
    assert ok is False
    assert trigger == "src/a.py"
    assert missing == ["docs/changes.md", "docs/specification.md"]


def test_docs_gate_passes_when_triggered_and_docs_present() -> None:
    check_docs_gate = _import_gate()
    ok, missing, trigger = check_docs_gate(
        ["plugins/p.py", "docs/changes.md", "docs/specification.md"],
        include=["src", "plugins"],
        exclude=["badguys", "patches"],
        required_files=["docs/changes.md", "docs/specification.md"],
    )
    assert ok is True
    assert missing == []
    assert trigger == "plugins/p.py"


def test_docs_gate_respects_required_files_override() -> None:
    check_docs_gate = _import_gate()
    ok, missing, trigger = check_docs_gate(
        ["src/a.py", "docs/changes.md"],
        include=["src"],
        exclude=["badguys", "patches"],
        required_files=["docs/changes.md"],
    )
    assert ok is True
    assert missing == []
    assert trigger == "src/a.py"
