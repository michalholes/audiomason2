"""FlowConfig bootstrap helpers for the import plugin.

Compatibility catalog projections are derived on demand from the active
authority layer. This module must not hold a hardcoded DEFAULT_CATALOG truth
artifact.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from plugins.file_io.service import FileService

from .flow_config_defaults import DEFAULT_FLOW_CONFIG, ensure_flow_config_exists


def _build_default_catalog() -> dict[str, object]:
    from .step_catalog import build_default_step_catalog_projection

    projection = build_default_step_catalog_projection()
    steps: list[dict[str, object]] = []
    for step_id in projection:
        entry = projection[step_id]
        steps.append(
            {
                "step_id": step_id,
                "title": str(entry.get("title") or step_id),
                "computed_only": step_id in {"plan_preview_batch", "processing"},
                "fields": [],
            }
        )
    return {"version": 1, "steps": steps}


class _DerivedCatalogView(Mapping[str, object]):
    def _current(self) -> dict[str, object]:
        return _build_default_catalog()

    def __getitem__(self, key: str) -> object:
        return self._current()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._current())

    def __len__(self) -> int:
        return len(self._current())

    def get(self, key: str, default: object = None) -> object:
        return self._current().get(key, default)


DEFAULT_CATALOG: Mapping[str, object] = _DerivedCatalogView()

__all__ = ["DEFAULT_CATALOG", "DEFAULT_FLOW_CONFIG", "ensure_default_models"]


def ensure_default_models(fs: FileService) -> dict[str, bool]:
    """Compatibility shim that bootstraps only FlowConfig."""
    flow_cfg_status = ensure_flow_config_exists(fs)
    return {
        "catalog_created": False,
        "flow_created": False,
        "flow_config_created": flow_cfg_status["flow_config_created"],
    }
