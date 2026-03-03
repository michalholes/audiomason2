"""WizardDefinition editor for import wizard (plugin: import).

This is a CLI-only editor provided by the import plugin.

Rules:
- load/save WizardDefinition under WIZARDS root
- validate before any save
- deterministic JSON formatting

ASCII-only.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from typing import Any

from .editor import EditorResult
from .engine import ImportWizardEngine
from .errors import error_envelope
from .wizard_definition_model import (
    canonicalize_wizard_definition,
    validate_wizard_definition_constraints_v2,
    validate_wizard_definition_structure,
)
from .wizard_editor_storage import load_wizard_definition, save_wizard_definition


def show_wizard_definition(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    wd = load_wizard_definition(fs)
    return EditorResult(ok=True, data=wd)


def validate_wizard_definition(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    try:
        wd = load_wizard_definition(fs)
        return EditorResult(ok=True, data={"ok": True, "wizard_definition": wd})
    except Exception as e:
        return EditorResult(
            ok=False,
            data=error_envelope(
                "VALIDATION_ERROR",
                "wizard_definition is invalid",
                details=[{"path": "$.wizard_definition", "reason": str(e), "meta": {}}],
            ),
        )


def save_wizard_definition_validated(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    try:
        wd = load_wizard_definition(fs)
        save_wizard_definition(fs, wd)
        return EditorResult(ok=True, data={"ok": True})
    except Exception as e:
        return EditorResult(
            ok=False,
            data=error_envelope(
                "VALIDATION_ERROR",
                "wizard_definition is invalid",
                details=[{"path": "$.wizard_definition", "reason": str(e), "meta": {}}],
            ),
        )


def edit_wizard_definition_interactive(engine: ImportWizardEngine) -> EditorResult:
    fs = engine.get_file_service()
    current = load_wizard_definition(fs)
    return _edit_interactive(
        title="wizard_definition",
        current=current,
        validate_fn=_validate_for_edit,
        save_fn=lambda obj: save_wizard_definition(fs, obj),
    )


def _validate_for_edit(obj: Any) -> dict[str, Any]:
    try:
        validate_wizard_definition_structure(obj)
        wd_canon = canonicalize_wizard_definition(obj)
        if isinstance(wd_canon, dict) and wd_canon.get("version") == 2:
            validate_wizard_definition_constraints_v2(wd_canon)
        return {"ok": True}
    except Exception as e:
        return error_envelope(
            "VALIDATION_ERROR",
            "wizard_definition is invalid",
            details=[{"path": "$.wizard_definition", "reason": str(e), "meta": {}}],
        )


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
                "message_id": "import.wizard_editor.invalid_json",
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
            ok=False,
            data={"ok": False, "rejected": True, "reason": "not_confirmed"},
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
