"""Interactive editor for import wizard models (plugin: import).

This is a CLI-only editor provided by the import plugin.

No engine semantics are changed. Only future sessions are affected
because sessions persist a frozen effective_model.json at creation time.

ASCII-only.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .editor_storage import (
    list_history,
    load_catalog,
    load_flow,
    load_flow_config,
    reset_flow_config,
    rollback,
    save_flow_config,
)
from .engine import ImportWizardEngine


@dataclass(frozen=True)
class EditorResult:
    ok: bool
    data: Any


def show_catalog(engine: ImportWizardEngine) -> EditorResult:
    catalog = load_catalog(engine.get_file_service())
    return EditorResult(ok=True, data=catalog)


def show_flow(engine: ImportWizardEngine) -> EditorResult:
    flow = load_flow(engine.get_file_service())
    return EditorResult(ok=True, data=flow)


def validate_catalog(engine: ImportWizardEngine) -> EditorResult:
    catalog = load_catalog(engine.get_file_service())
    result = engine.validate_catalog(catalog)
    return EditorResult(ok=bool(result.get("ok")), data=result)


def validate_flow(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    catalog = load_catalog(fs)
    flow = load_flow(fs)
    result = engine.validate_flow(flow, catalog)
    return EditorResult(ok=bool(result.get("ok")), data=result)


def save_catalog_validated(engine: ImportWizardEngine) -> EditorResult:
    return EditorResult(
        ok=False,
        data={
            "error": {
                "code": "INVARIANT_VIOLATION",
                "message": "catalog is immutable; editor may only modify flow_config",
                "details": [{"path": "$.catalog", "reason": "immutable", "meta": {}}],
            }
        },
    )


def save_flow_validated(engine: ImportWizardEngine) -> EditorResult:
    return EditorResult(
        ok=False,
        data={
            "error": {
                "code": "INVARIANT_VIOLATION",
                "message": "flow is immutable; editor may only modify flow_config",
                "details": [{"path": "$.flow", "reason": "immutable", "meta": {}}],
            }
        },
    )


def preview_effective_model(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    catalog = load_catalog(fs)
    flow = load_flow(fs)
    result = engine.preview_effective_model(catalog, flow)
    return EditorResult(ok=True, data=result)


def edit_catalog_interactive(engine: ImportWizardEngine) -> EditorResult:
    return EditorResult(
        ok=False,
        data={
            "error": {
                "code": "INVARIANT_VIOLATION",
                "message": "catalog is immutable; editor may only modify flow_config",
                "details": [{"path": "$.catalog", "reason": "immutable", "meta": {}}],
            }
        },
    )


def edit_flow_interactive(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    current = load_flow_config(fs)
    return _edit_interactive(
        title="flow_config",
        current=current,
        validate_fn=lambda obj: engine.validate_flow_config(obj),
        save_fn=lambda obj: save_flow_config(fs, obj),
    )


def reset_catalog_to_defaults(engine: ImportWizardEngine) -> EditorResult:
    return EditorResult(
        ok=False,
        data={
            "error": {
                "code": "INVARIANT_VIOLATION",
                "message": "catalog is immutable; editor may only modify flow_config",
                "details": [{"path": "$.catalog", "reason": "immutable", "meta": {}}],
            }
        },
    )


def reset_flow_to_defaults(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    reset_flow_config(fs)
    return EditorResult(ok=True, data={"ok": True})


def history(engine: ImportWizardEngine, *, kind: str) -> EditorResult:
    fs = engine.get_file_service()
    return EditorResult(ok=True, data={"items": list_history(fs, kind=kind)})


def rollback_history(engine: ImportWizardEngine, *, kind: str, fingerprint: str) -> EditorResult:
    fs = engine.get_file_service()
    try:
        rollback(fs, kind=kind, fingerprint=fingerprint)
        return EditorResult(ok=True, data={"ok": True})
    except Exception as e:
        return EditorResult(ok=False, data={"error": str(e)})


def _edit_interactive(
    *,
    title: str,
    current: Any,
    validate_fn: Any,
    save_fn: Any,
) -> EditorResult:
    sys.stdout.write(_banner_lines(title))
    sys.stdout.write(json.dumps(current, indent=2, sort_keys=True, ensure_ascii=True) + "\n")
    sys.stdout.write("\nPaste replacement JSON. End with a single line containing only '.'\n")
    sys.stdout.flush()

    text = "\n".join(_read_until_dot(sys.stdin))
    try:
        new_obj = json.loads(text)
    except Exception as e:
        return EditorResult(
            ok=False,
            data={
                "code": "invalid_json",
                "message_id": "import.editor.invalid_json",
                "default_message": "Input is not valid JSON",
                "details": {"error": str(e)},
            },
        )

    validation = validate_fn(new_obj)
    if not bool(validation.get("ok")):
        return EditorResult(ok=False, data=validation)

    sys.stdout.write("Validation OK. Save changes? Type 'yes' to confirm: ")
    sys.stdout.flush()
    answer = sys.stdin.readline().strip().lower()
    if answer != "yes":
        return EditorResult(
            ok=False, data={"ok": False, "rejected": True, "reason": "not_confirmed"}
        )

    save_fn(new_obj)
    return EditorResult(ok=True, data={"ok": True})


def _banner_lines(title: str) -> str:
    return f"=== Import Wizard editor: {title} ===\nCurrent JSON follows.\n\n"


def _read_until_dot(stream: Any) -> Iterable[str]:
    for line in stream:
        line = line.rstrip("\n")
        if line == ".":
            break
        yield line
