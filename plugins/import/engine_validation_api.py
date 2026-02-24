"""Import engine validation helper APIs.

Kept separate to reduce size of the main engine module.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .engine_util import _exception_envelope
from .models import CatalogModel, FlowModel, validate_models


def validate_catalog_impl(*, engine: Any, catalog_json: Any) -> dict[str, Any]:
    """Validate catalog JSON using engine invariants.

    Returns {"ok": True} on success, or a canonical error envelope.
    """
    try:
        _ = engine
        if not isinstance(catalog_json, dict):
            raise ValueError("catalog_json must be an object")
        _ = CatalogModel.from_dict(catalog_json)
        return {"ok": True}
    except Exception as e:
        return _exception_envelope(e)


def validate_flow_impl(*, engine: Any, flow_json: Any, catalog_json: Any) -> dict[str, Any]:
    """Validate flow JSON against the catalog using engine invariants."""
    try:
        _ = engine
        if not isinstance(catalog_json, dict):
            raise ValueError("catalog_json must be an object")
        if not isinstance(flow_json, dict):
            raise ValueError("flow_json must be an object")
        catalog = CatalogModel.from_dict(catalog_json)
        flow = FlowModel.from_dict(flow_json)
        validate_models(catalog, flow)
        return {"ok": True}
    except Exception as e:
        return _exception_envelope(e)


def validate_flow_config_impl(*, engine: Any, flow_config_json: Any) -> dict[str, Any]:
    """Validate FlowConfig JSON."""
    try:
        if not isinstance(flow_config_json, dict):
            raise ValueError("flow_config_json must be an object")
        _ = engine._normalize_flow_config(flow_config_json)
        return {"ok": True}
    except Exception as e:
        return _exception_envelope(e)
