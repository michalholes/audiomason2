"""Runtime and validation coverage for the generic call.invoke primitive."""

from __future__ import annotations

import asyncio
from importlib import import_module

import pytest

call_v1 = import_module("plugins.import.primitives.call_v1")
FieldSchemaValidationError = import_module(
    "plugins.import.field_schema_validation"
).FieldSchemaValidationError
validate_wizard_definition_v3_structure = import_module(
    "plugins.import.dsl.wizard_definition_v3_model"
).validate_wizard_definition_v3_structure
validate_wizard_definition_v3_against_registry = import_module(
    "plugins.import.dsl.wizard_definition_v3_model"
).validate_wizard_definition_v3_against_registry
baseline_registry_entries = import_module("plugins.import.primitives").baseline_registry_entries
resolve_inputs = import_module("plugins.import.dsl.interpreter_v3").resolve_inputs


def _registry() -> dict[str, object]:
    return {"registry_version": 1, "primitives": baseline_registry_entries()}


def _call_program(inputs: dict[str, object]) -> dict[str, object]:
    return {
        "version": 3,
        "entry_step_id": "invoke",
        "nodes": [
            {
                "step_id": "invoke",
                "op": {
                    "primitive_id": "call.invoke",
                    "primitive_version": 1,
                    "inputs": inputs,
                    "writes": [
                        {
                            "to_path": "$.state.vars.call.result",
                            "value": {"expr": "$.op.outputs.result"},
                        }
                    ],
                },
            }
        ],
        "edges": [],
    }


def test_call_invoke_execute_inline_returns_published_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _inline_callable(*, greeting: str) -> dict[str, str]:
        return {"message": greeting}

    monkeypatch.setattr(
        call_v1,
        "_resolve_published_callable_binding",
        lambda **_: call_v1._ResolvedCallableBinding(
            operation_id="demo.echo",
            execution_mode="inline",
            plugin_obj=object(),
            callable_obj=_inline_callable,
        ),
    )

    out = call_v1.execute(
        "call.invoke",
        1,
        {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {"greeting": "ahoj"},
        },
    )

    assert out == {"result": {"message": "ahoj"}, "error": None}


def test_call_invoke_execute_job_works_inside_running_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Plugin:
        async def execute_job(self, job: dict[str, object]) -> dict[str, object]:
            return {"job": dict(job), "status": "ok"}

    def _build_job(*, author: str, title: str) -> dict[str, str]:
        return {"author": author, "title": title}

    monkeypatch.setattr(
        call_v1,
        "_resolve_published_callable_binding",
        lambda **_: call_v1._ResolvedCallableBinding(
            operation_id="demo.validate",
            execution_mode="job",
            plugin_obj=_Plugin(),
            callable_obj=_build_job,
        ),
    )

    async def _run() -> dict[str, object]:
        return call_v1.execute(
            "call.invoke",
            1,
            {
                "operation_id": "demo.validate",
                "execution_mode": "job",
                "args": {"author": "Meyrink", "title": "Preparat"},
            },
        )

    out = asyncio.run(_run())

    assert out == {
        "result": {"job": {"author": "Meyrink", "title": "Preparat"}, "status": "ok"},
        "error": None,
    }


def test_wizard_definition_v3_accepts_call_invoke_with_exact_inputs() -> None:
    wd = _call_program(
        {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {"greeting": "ahoj"},
        }
    )

    validate_wizard_definition_v3_structure(wd)
    validate_wizard_definition_v3_against_registry(wd, _registry())


def test_wizard_definition_v3_rejects_call_invoke_unknown_field() -> None:
    wd = _call_program(
        {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {},
            "unexpected": True,
        }
    )

    with pytest.raises(FieldSchemaValidationError) as excinfo:
        validate_wizard_definition_v3_structure(wd)

    assert excinfo.value.path == "$.nodes[0].op.inputs.unexpected"
    assert excinfo.value.reason == "unknown_field"


def test_wizard_definition_v3_rejects_call_invoke_invalid_execution_mode() -> None:
    wd = _call_program(
        {
            "operation_id": "demo.echo",
            "execution_mode": "stream",
            "args": {},
        }
    )

    with pytest.raises(FieldSchemaValidationError) as excinfo:
        validate_wizard_definition_v3_structure(wd)

    assert excinfo.value.path == "$.nodes[0].op.inputs.execution_mode"
    assert excinfo.value.reason == "invalid_enum"


def test_call_invoke_capture_mode_returns_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**_: object) -> object:
        raise RuntimeError("offline")

    monkeypatch.setattr(
        call_v1,
        "_resolve_published_callable_binding",
        lambda **_: call_v1._ResolvedCallableBinding(
            operation_id="demo.echo",
            execution_mode="inline",
            plugin_obj=object(),
            callable_obj=_boom,
        ),
    )

    out = call_v1.execute(
        "call.invoke",
        1,
        {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "error_mode": "capture",
            "args": {},
        },
    )

    assert out["result"] is None
    assert out["error"] == {"type": "RuntimeError", "message": "offline"}


def test_call_invoke_injects_generic_runtime_file_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_fs = object()

    def _inline_callable(*, file_service: object, greeting: str) -> dict[str, object]:
        return {"file_service": file_service, "message": greeting}

    monkeypatch.setattr(call_v1, "file_service_from_resolver", lambda _resolver: sentinel_fs)
    monkeypatch.setattr(
        call_v1,
        "_resolve_published_callable_binding",
        lambda **_: call_v1._ResolvedCallableBinding(
            operation_id="demo.echo",
            execution_mode="inline",
            plugin_obj=object(),
            callable_obj=_inline_callable,
        ),
    )

    out = call_v1.execute(
        "call.invoke",
        1,
        {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {"greeting": "ahoj"},
        },
    )

    assert out == {
        "result": {"file_service": sentinel_fs, "message": "ahoj"},
        "error": None,
    }


def test_call_invoke_prefers_runtime_bootstrap_file_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel_fs = object()

    class _DetachedRuntime:
        def get_file_service(self) -> object:
            return sentinel_fs

    def _inline_callable(*, file_service: object, greeting: str) -> dict[str, object]:
        return {"file_service": file_service, "message": greeting}

    monkeypatch.setattr(
        call_v1,
        "rehydrate_detached_runtime_from_bootstrap",
        lambda *, bootstrap: _DetachedRuntime(),
    )
    monkeypatch.setattr(
        call_v1,
        "_resolve_published_callable_binding",
        lambda **_: call_v1._ResolvedCallableBinding(
            operation_id="demo.echo",
            execution_mode="inline",
            plugin_obj=object(),
            callable_obj=_inline_callable,
        ),
    )

    out = call_v1.execute(
        "call.invoke",
        1,
        {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {"greeting": "ahoj"},
        },
        state={"vars": {"runtime": {"detached_runtime": {"version": 1}}}},
    )

    assert out == {
        "result": {"file_service": sentinel_fs, "message": "ahoj"},
        "error": None,
    }


def test_call_invoke_resolves_nested_expr_args() -> None:
    step = {
        "primitive_id": "call.invoke",
        "primitive_version": 1,
        "inputs": {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {
                "author": {"expr": "$.state.vars.author"},
                "title": {"expr": "$.state.vars.title"},
            },
        },
    }
    state = {"vars": {"author": "Meyrink", "title": "Preparat"}, "answers": {}, "jobs": {}}

    out = resolve_inputs(step, state)

    assert out["args"] == {"author": "Meyrink", "title": "Preparat"}


def test_call_invoke_resolves_nested_expr_args_from_state_source() -> None:
    step = {
        "primitive_id": "call.invoke",
        "primitive_version": 1,
        "inputs": {
            "operation_id": "demo.echo",
            "execution_mode": "inline",
            "args": {
                "source_root": {"expr": "$.state.source.root"},
                "source_relative_path": {"expr": "$.state.source.relative_path"},
            },
        },
    }
    state = {
        "source": {"root": "inbox", "relative_path": "Shelf/Book"},
        "vars": {},
        "answers": {},
        "jobs": {},
    }

    out = resolve_inputs(step, state)

    assert out["args"] == {
        "source_root": "inbox",
        "source_relative_path": "Shelf/Book",
    }
