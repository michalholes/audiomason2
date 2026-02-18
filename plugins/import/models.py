"""Data models for the import wizard engine.

The engine loads catalog/catalog.json and flow/current.json under the WIZARDS root.
Only minimal schema validation is implemented here.

ASCII-only.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from .errors import ModelLoadError, ModelValidationError

_REQUIRED_STEP_IDS = {
    "select_authors",
    "select_books",
    "plan_preview_batch",
    "effective_author_title",
    "filename_policy",
    "covers_policy",
    "id3_policy",
    "audio_processing",
    "publish_policy",
    "delete_source_policy",
    "conflict_policy",
    "parallelism",
    "final_summary_confirm",
    "resolve_conflicts_batch",
}


_ALLOWED_FIELD_TYPES = {"bool", "int", "str", "list[int]", "list[str]"}


@dataclass(frozen=True)
class CatalogModel:
    version: int
    steps: list[dict[str, Any]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogModel:
        if not isinstance(data, dict):
            raise ModelLoadError("Catalog must be an object")
        version = data.get("version")
        steps = data.get("steps")
        if not isinstance(version, int):
            raise ModelLoadError("Catalog missing valid 'version' (int)")
        if not isinstance(steps, list):
            raise ModelLoadError("Catalog missing valid 'steps' list")
        normalized_steps: list[dict[str, Any]] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ModelLoadError(f"Catalog step[{i}] must be an object")
            _validate_step_schema(step, i)
            normalized_steps.append(step)
        return cls(version=version, steps=normalized_steps)

    def step_ids(self) -> set[str]:
        ids: set[str] = set()
        for step in self.steps:
            sid = step.get("step_id")
            if isinstance(sid, str) and sid:
                ids.add(sid)
        return ids


@dataclass(frozen=True)
class FlowNode:
    step_id: str
    next_step_id: str | None
    prev_step_id: str | None


@dataclass(frozen=True)
class FlowModel:
    version: int
    entry_step_id: str
    nodes: list[FlowNode]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FlowModel:
        if not isinstance(data, dict):
            raise ModelLoadError("Flow must be an object")
        version = data.get("version")
        entry = data.get("entry_step_id")
        nodes_raw = data.get("nodes")
        if not isinstance(version, int):
            raise ModelLoadError("Flow missing valid 'version' (int)")
        if not isinstance(entry, str) or not entry:
            raise ModelLoadError("Flow missing valid 'entry_step_id'")
        if not isinstance(nodes_raw, list):
            raise ModelLoadError("Flow missing valid 'nodes' list")

        nodes: list[FlowNode] = []

        # Accept either list[str] (implicit linear) or list[dict].
        if all(isinstance(n, str) for n in nodes_raw):
            step_ids = [str(x) for x in nodes_raw]
            for i, step_id in enumerate(step_ids):
                next_id = step_ids[i + 1] if i + 1 < len(step_ids) else None
                prev_id = step_ids[i - 1] if i - 1 >= 0 else None
                nodes.append(FlowNode(step_id=step_id, next_step_id=next_id, prev_step_id=prev_id))
        else:
            for i, n in enumerate(nodes_raw):
                if not isinstance(n, dict):
                    raise ModelLoadError(f"Flow node[{i}] must be an object")
                sid_any = n.get("step_id")
                if not isinstance(sid_any, str) or not sid_any:
                    raise ModelLoadError(f"Flow node[{i}] missing valid 'step_id'")
                sid: str = sid_any
                next_id = n.get("next_step_id")
                prev_id = n.get("prev_step_id")
                if next_id is not None and not isinstance(next_id, str):
                    raise ModelLoadError(f"Flow node[{i}] invalid 'next_step_id'")
                if prev_id is not None and not isinstance(prev_id, str):
                    raise ModelLoadError(f"Flow node[{i}] invalid 'prev_step_id'")
                nodes.append(
                    FlowNode(
                        step_id=sid,
                        next_step_id=next_id,
                        prev_step_id=prev_id,
                    )
                )

        return cls(version=version, entry_step_id=entry, nodes=nodes)

    def node_map(self) -> dict[str, FlowNode]:
        return {n.step_id: n for n in self.nodes}


def validate_models(catalog: CatalogModel, flow: FlowModel) -> None:
    step_ids = catalog.step_ids()

    missing = sorted(_REQUIRED_STEP_IDS - step_ids)
    if missing:
        raise ModelValidationError(f"Catalog missing required step_ids: {missing}")

    node_ids = {n.step_id for n in flow.nodes}
    if flow.entry_step_id not in node_ids:
        raise ModelValidationError("Flow entry_step_id must exist in nodes")

    # Minimal invariants: final confirmation and conflict gate must exist in flow nodes.
    for required in ("final_summary_confirm", "conflict_policy"):
        if required not in node_ids:
            raise ModelValidationError(f"Flow missing required step node: {required}")

    # Ensure next/prev references are within node_ids when present.
    for n in flow.nodes:
        if n.next_step_id is not None and n.next_step_id not in node_ids:
            raise ModelValidationError(
                f"Flow node '{n.step_id}' references missing next_step_id '{n.next_step_id}'"
            )
        if n.prev_step_id is not None and n.prev_step_id not in node_ids:
            raise ModelValidationError(
                f"Flow node '{n.step_id}' references missing prev_step_id '{n.prev_step_id}'"
            )

    reachable = _reachable_step_ids(flow)
    if "final_summary_confirm" not in reachable:
        raise ModelValidationError("Flow must reach final_summary_confirm from entry_step_id")


def _require_ascii_str(value: Any, *, field: str, step_index: int) -> str:
    if not isinstance(value, str) or not value:
        raise ModelValidationError(
            f"Catalog step[{step_index}] missing valid '{field}' (non-empty string)"
        )
    try:
        value.encode("ascii")
    except UnicodeEncodeError as e:
        raise ModelValidationError(
            f"Catalog step[{step_index}] field '{field}' must be ASCII-only"
        ) from e
    return value


def _require_bool(value: Any, *, field: str, step_index: int) -> bool:
    if not isinstance(value, bool):
        raise ModelValidationError(f"Catalog step[{step_index}] missing valid '{field}' (bool)")
    return value


def _validate_step_schema(step: dict[str, Any], step_index: int) -> None:
    _ = _require_ascii_str(step.get("step_id"), field="step_id", step_index=step_index)
    _ = _require_ascii_str(step.get("title"), field="title", step_index=step_index)
    _ = _require_bool(step.get("computed_only"), field="computed_only", step_index=step_index)

    fields_any = step.get("fields")
    if not isinstance(fields_any, list):
        raise ModelValidationError(f"Catalog step[{step_index}] missing valid 'fields' (list)")

    for i, f in enumerate(fields_any):
        if not isinstance(f, dict):
            raise ModelValidationError(f"Catalog step[{step_index}] field[{i}] must be an object")
        name = f.get("name")
        ftype = f.get("type")
        required = f.get("required")
        _ = _require_ascii_str(name, field="name", step_index=step_index)
        _ = _require_ascii_str(ftype, field="type", step_index=step_index)
        _ = _require_bool(required, field="required", step_index=step_index)
        if str(ftype) not in _ALLOWED_FIELD_TYPES:
            raise ModelValidationError(
                f"Catalog step[{step_index}] field[{i}] has unsupported type '{ftype}'"
            )
        constraints = f.get("constraints", {})
        if not isinstance(constraints, dict):
            raise ModelValidationError(
                f"Catalog step[{step_index}] field[{i}] constraints must be an object"
            )


def _reachable_step_ids(flow: FlowModel) -> set[str]:
    node_map = flow.node_map()
    start = flow.entry_step_id
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        cur = queue.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        node = node_map.get(cur)
        if node is None:
            continue
        if node.next_step_id is not None and node.next_step_id not in visited:
            queue.append(node.next_step_id)
    return visited
