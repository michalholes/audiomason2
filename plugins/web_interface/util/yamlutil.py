from __future__ import annotations

from typing import Any


def safe_load_yaml(text: str) -> Any:
    try:
        import yaml
    except Exception:
        return None
    try:
        return yaml.safe_load(text)
    except Exception:
        return None


def safe_dump_yaml(obj: Any) -> str | None:
    try:
        import yaml
    except Exception:
        return None
    try:
        return yaml.safe_dump(obj, sort_keys=False)
    except Exception:
        return None
