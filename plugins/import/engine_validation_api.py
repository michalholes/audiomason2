"""Import engine validation helper APIs.

Kept separate to reduce size of the main engine module.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .engine_util import exception_envelope, is_str_object_dict
from .models import CatalogModel, FlowModel, validate_models

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def validate_catalog_impl(*, engine: ImportWizardEngine, catalog_json: object) -> dict[str, object]:
    """Validate catalog JSON using engine invariants.

    Returns {"ok": True} on success, or a canonical error envelope.
    """
    try:
        _ = engine
        if not is_str_object_dict(catalog_json):
            raise ValueError("catalog_json must be an object")
        _ = CatalogModel.from_dict(catalog_json)
        return {"ok": True}
    except Exception as e:
        return exception_envelope(e)


def validate_flow_impl(
    *, engine: ImportWizardEngine, flow_json: object, catalog_json: object
) -> dict[str, object]:
    """Validate flow JSON against the catalog using engine invariants."""
    try:
        _ = engine
        if not is_str_object_dict(catalog_json):
            raise ValueError("catalog_json must be an object")
        if not is_str_object_dict(flow_json):
            raise ValueError("flow_json must be an object")
        catalog = CatalogModel.from_dict(catalog_json)
        flow = FlowModel.from_dict(flow_json)
        validate_models(catalog, flow)
        return {"ok": True}
    except Exception as e:
        return exception_envelope(e)


def validate_flow_config_impl(
    *, engine: ImportWizardEngine, flow_config_json: object
) -> dict[str, object]:
    """Validate FlowConfig JSON."""
    try:
        if not is_str_object_dict(flow_config_json):
            raise ValueError("flow_config_json must be an object")
        _ = engine.normalize_flow_config(flow_config_json)
        return {"ok": True}
    except Exception as e:
        return exception_envelope(e)
