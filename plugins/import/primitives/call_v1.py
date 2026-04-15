"""Generic published wizard callable invocation primitive for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginNotFoundError
from audiomason.core.loader import PluginLoader
from audiomason.core.plugin_callable_authority import (
    RegisteredWizardCallable,
    resolve_registered_wizard_callable,
)
from audiomason.core.plugin_registry import PluginRegistry

from ..detached_runtime import rehydrate_detached_runtime_from_bootstrap
from ..file_io_facade import file_service_from_resolver


def _object_schema(*, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": list(required or []),
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, Any]] = [
    {
        "primitive_id": "call.invoke",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(required=["operation_id", "execution_mode", "args"]),
        "outputs_schema": _object_schema(required=["result", "error"]),
        "determinism_notes": (
            "deterministic published wizard callable resolution; behavior is fully "
            "declared by operation_id, execution_mode, args, and error_mode"
        ),
        "allowed_errors": ["INVARIANT_VIOLATION"],
    }
]


class _JobExecutorPlugin(Protocol):
    async def execute_job(self, job: dict[str, Any]) -> Any: ...


@dataclass(frozen=True)
class _ResolvedCallableBinding:
    operation_id: str
    execution_mode: str
    plugin_obj: object
    callable_obj: object


def _runtime_arg_file_service(*, state: dict[str, Any] | None = None) -> Any:
    vars_any = (state or {}).get("vars")
    vars_map = dict(vars_any) if isinstance(vars_any, dict) else {}
    runtime_any = vars_map.get("runtime")
    runtime = dict(runtime_any) if isinstance(runtime_any, dict) else {}
    bootstrap_any = runtime.get("detached_runtime")
    bootstrap = dict(bootstrap_any) if isinstance(bootstrap_any, dict) else {}
    if bootstrap:
        detached = rehydrate_detached_runtime_from_bootstrap(bootstrap=bootstrap)
        if detached is not None:
            return detached.get_file_service()
    return file_service_from_resolver(ConfigService())


_RUNTIME_ARG_FACTORIES: dict[str, Any] = {
    "file_service": _runtime_arg_file_service,
}


def _builtin_plugins_dir() -> Path:
    plugins_pkg = import_module("plugins")
    pkg_file = getattr(plugins_pkg, "__file__", None)
    if not isinstance(pkg_file, str) or not pkg_file:
        raise RuntimeError("plugins package path unavailable")
    return Path(pkg_file).resolve().parent


@lru_cache(maxsize=1)
def _callable_authority() -> tuple[PluginRegistry, PluginLoader]:
    registry = PluginRegistry(ConfigService())
    loader = PluginLoader(
        builtin_plugins_dir=_builtin_plugins_dir(),
        registry=registry,
    )
    return registry, loader


def _resolve_published_callable_binding(
    *,
    operation_id: str,
    expected_execution_mode: str,
) -> _ResolvedCallableBinding:
    registry, loader = _callable_authority()
    published = registry.resolve_wizard_callable(operation_id, loader=loader)
    if published.execution_mode != expected_execution_mode:
        raise RuntimeError(
            f"wizard_callable_execution_mode_mismatch:{operation_id}:{published.execution_mode}"
        )
    try:
        plugin_obj = loader.get_plugin(published.plugin_id)
    except PluginNotFoundError:
        plugin_obj = loader.load_plugin(published.manifest_path.parent, validate=False)
    callable_def = RegisteredWizardCallable(
        plugin_id=published.plugin_id,
        plugin_dir=published.manifest_path.parent,
        manifest_path=published.manifest_path,
        operation_id=published.operation_id,
        method_name=published.method_name,
        execution_mode=published.execution_mode,
    )
    callable_obj = resolve_registered_wizard_callable(
        plugin_obj=plugin_obj,
        callable_def=callable_def,
    )
    return _ResolvedCallableBinding(
        operation_id=published.operation_id,
        execution_mode=published.execution_mode,
        plugin_obj=plugin_obj,
        callable_obj=callable_obj,
    )


def _run_coro_blocking(coro: Any) -> Any:
    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result_box["result"] = loop.run_until_complete(coro)
            loop.run_until_complete(loop.shutdown_asyncgens())
        except BaseException as exc:  # pragma: no cover
            error_box["error"] = exc
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _runner()
    else:
        thread = threading.Thread(target=_runner, name="import-call-invoke")
        thread.start()
        thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box.get("result")


def _execute_inline(*, binding: _ResolvedCallableBinding, args: dict[str, Any]) -> Any:
    callable_obj = cast(Any, binding.callable_obj)
    return callable_obj(**dict(args))


def _execute_job(*, binding: _ResolvedCallableBinding, args: dict[str, Any]) -> Any:
    build_job = cast(Any, binding.callable_obj)
    job = build_job(**dict(args))
    if not isinstance(job, dict):
        raise RuntimeError("wizard_callable_job_builder_must_return_object")
    plugin = cast(_JobExecutorPlugin, binding.plugin_obj)
    execute_job = getattr(plugin, "execute_job", None)
    if not callable(execute_job):
        raise RuntimeError("wizard_callable_job_plugin_missing_execute_job")
    return _run_coro_blocking(execute_job(dict(job)))


def _bind_runtime_args(
    *,
    callable_obj: object,
    args: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bound = dict(args)
    if not callable(callable_obj):
        return bound
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return bound
    for name in parameters:
        if name in bound:
            continue
        factory = _RUNTIME_ARG_FACTORIES.get(name)
        if factory is None:
            continue
        bound[name] = factory(state=state)
    return bound


def execute(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    if primitive_id != "call.invoke":
        raise ValueError("unknown call primitive")
    operation_id = str(inputs.get("operation_id") or "")
    execution_mode = str(inputs.get("execution_mode") or "").strip().lower()
    error_mode = str(inputs.get("error_mode") or "raise").strip().lower()
    args_any = inputs.get("args")
    args = dict(args_any) if isinstance(args_any, dict) else {}
    if not operation_id:
        raise ValueError("operation_id is required")
    if execution_mode not in {"inline", "job"}:
        raise ValueError("execution_mode must be inline or job")
    if error_mode not in {"raise", "capture"}:
        raise ValueError("error_mode must be raise or capture")
    try:
        binding = _resolve_published_callable_binding(
            operation_id=operation_id,
            expected_execution_mode=execution_mode,
        )
        if execution_mode == "inline":
            return {
                "result": _execute_inline(
                    binding=binding,
                    args=_bind_runtime_args(
                        callable_obj=binding.callable_obj,
                        args=args,
                        state=state,
                    ),
                ),
                "error": None,
            }
        return {
            "result": _execute_job(
                binding=binding,
                args=_bind_runtime_args(
                    callable_obj=binding.callable_obj,
                    args=args,
                    state=state,
                ),
            ),
            "error": None,
        }
    except Exception as exc:
        if error_mode != "capture":
            raise
        return {
            "result": None,
            "error": {
                "type": exc.__class__.__name__,
                "message": str(exc) or exc.__class__.__name__,
            },
        }


__all__ = ["REGISTRY_ENTRIES", "execute"]
