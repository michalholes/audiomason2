"""Core-owned wizard callable authority helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TypeGuard, cast

from audiomason.core.errors import PluginError, PluginValidationError
from audiomason.core.serde import json_loads_object

_ALLOWED_EXECUTION_MODES = {"inline", "job"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_str_any_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _operation_id(definition: RegisteredWizardCallable) -> str:
    return definition.operation_id


@dataclass(frozen=True)
class RegisteredWizardCallable:
    """Registry-owned callable authority record."""

    plugin_id: str
    plugin_dir: Path
    manifest_path: Path
    operation_id: str
    method_name: str
    execution_mode: str


def _ensure_ascii_text(value: object, *, field: str, manifest_path: Path) -> str:
    if not isinstance(value, str) or not value:
        raise PluginValidationError(
            f"Invalid callable manifest field '{field}' in {manifest_path}: "
            "must be a non-empty string"
        )
    if not value.isascii():
        raise PluginValidationError(
            f"Invalid callable manifest field '{field}' in {manifest_path}: must be ASCII"
        )
    return value


def _validate_manifest_pointer(pointer: str, *, plugin_dir: Path) -> Path:
    pointer_text = _ensure_ascii_text(
        pointer,
        field="wizard_callable_manifest_pointer",
        manifest_path=plugin_dir / "plugin.yaml",
    )
    pointer_path = PurePosixPath(pointer_text)
    if pointer_path.is_absolute() or ".." in pointer_path.parts:
        raise PluginValidationError(
            f"Invalid wizard_callable_manifest_pointer in {plugin_dir / 'plugin.yaml'}: "
            "must be a relative in-plugin path"
        )
    return plugin_dir / Path(pointer_text)


def _load_manifest_json(manifest_path: Path) -> dict[str, object]:
    if not manifest_path.exists():
        raise PluginValidationError(f"Wizard callable manifest not found: {manifest_path}")
    try:
        data = json_loads_object(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise PluginValidationError(
            f"Failed to load wizard callable manifest from {manifest_path}: {exc}"
        ) from exc
    if not _is_str_any_dict(data):
        raise PluginValidationError(
            f"Invalid wizard callable manifest {manifest_path}: root must be an object"
        )
    return data


def load_wizard_callable_definitions(
    *,
    plugin_id: str,
    plugin_dir: Path,
    manifest_pointer: str | None,
) -> tuple[RegisteredWizardCallable, ...]:
    """Load provider-owned callable publication data from the manifest pointer."""
    if manifest_pointer is None:
        return ()

    manifest_path = _validate_manifest_pointer(manifest_pointer, plugin_dir=plugin_dir)
    data = _load_manifest_json(manifest_path)

    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise PluginValidationError(
            f"Invalid wizard callable manifest {manifest_path}: schema_version must be 1"
        )

    operations = data.get("operations")
    if not isinstance(operations, list):
        raise PluginValidationError(
            f"Invalid wizard callable manifest {manifest_path}: operations must be a list"
        )
    operations_list = cast(list[object], operations)

    seen_operation_ids: set[str] = set()
    definitions: list[RegisteredWizardCallable] = []
    for index, item_obj in enumerate(operations_list):
        if not _is_str_any_dict(item_obj):
            raise PluginValidationError(
                f"Invalid wizard callable manifest entry {index} in {manifest_path}: "
                "operation must be an object"
            )
        item = item_obj

        operation_id = _ensure_ascii_text(
            item.get("operation_id"),
            field=f"operations[{index}].operation_id",
            manifest_path=manifest_path,
        )
        if operation_id in seen_operation_ids:
            raise PluginValidationError(
                f"Duplicate wizard callable operation_id '{operation_id}' in {manifest_path}"
            )
        seen_operation_ids.add(operation_id)

        method_name = _ensure_ascii_text(
            item.get("method_name"),
            field=f"operations[{index}].method_name",
            manifest_path=manifest_path,
        )
        if _IDENTIFIER_RE.fullmatch(method_name) is None:
            raise PluginValidationError(
                f"Invalid wizard callable method_name '{method_name}' in {manifest_path}: "
                "must be a Python identifier"
            )

        execution_mode = _ensure_ascii_text(
            item.get("execution_mode"),
            field=f"operations[{index}].execution_mode",
            manifest_path=manifest_path,
        )
        if execution_mode not in _ALLOWED_EXECUTION_MODES:
            raise PluginValidationError(
                f"Invalid wizard callable execution_mode '{execution_mode}' in {manifest_path}: "
                "must be one of ['inline', 'job']"
            )

        definitions.append(
            RegisteredWizardCallable(
                plugin_id=plugin_id,
                plugin_dir=plugin_dir,
                manifest_path=manifest_path,
                operation_id=operation_id,
                method_name=method_name,
                execution_mode=execution_mode,
            )
        )

    return tuple(sorted(definitions, key=_operation_id))


def resolve_registered_wizard_callable(
    *,
    plugin_obj: object,
    callable_def: RegisteredWizardCallable,
) -> object:
    """Resolve a published callable from a plugin instance via the registry contract."""
    method_obj: object = getattr(plugin_obj, callable_def.method_name, None)
    if not callable(method_obj):
        raise PluginError(
            f"Published wizard callable '{callable_def.operation_id}' is missing method "
            f"'{callable_def.method_name}' on plugin '{callable_def.plugin_id}'"
        )
    return method_obj


__all__ = [
    "RegisteredWizardCallable",
    "load_wizard_callable_definitions",
    "resolve_registered_wizard_callable",
]
