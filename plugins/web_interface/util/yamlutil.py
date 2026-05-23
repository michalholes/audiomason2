from __future__ import annotations

from audiomason.core.serde import yaml_safe_load_text


def safe_load_yaml(text: str) -> object:
    try:
        return yaml_safe_load_text(text)
    except Exception:
        return None


def safe_dump_yaml(obj: object) -> str | None:
    try:
        import yaml
    except Exception:
        return None
    try:
        rendered = yaml.safe_dump(obj, sort_keys=False)
        return rendered
    except Exception:
        return None
