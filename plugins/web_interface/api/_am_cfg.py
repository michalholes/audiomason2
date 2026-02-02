from __future__ import annotations

import re

from ..util.paths import am_config_path
from ..util.yamlutil import safe_dump_yaml, safe_load_yaml


def read_am_config_text() -> str:
    path = am_config_path()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_am_config_text(text: str) -> None:
    path = am_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_inbox_dir(text: str) -> str | None:
    m = re.search(r"(?m)^\s*inbox_dir\s*:\s*(.+?)\s*$", text)
    if not m:
        return None
    v = m.group(1).strip()
    # strip quotes
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1]
    return v


def get_disabled_plugins(text: str) -> list[str]:
    # Prefer real YAML parser if available
    obj = safe_load_yaml(text)
    if isinstance(obj, dict):
        plugins = obj.get("plugins")
        if isinstance(plugins, dict):
            disabled = plugins.get("disabled")
            if isinstance(disabled, list):
                return [str(x) for x in disabled]
    # Fallback: parse inline list: disabled: [a, b]
    m = re.search(r"(?m)^\s*disabled\s*:\s*\[(.*?)\]\s*$", text)
    if m:
        inner = m.group(1).strip()
        if not inner:
            return []
        return [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
    # Fallback: parse block list
    lines = text.splitlines()
    disabled: list[str] = []
    in_plugins = False
    in_disabled = False
    for ln in lines:
        if re.match(r"^\s*plugins\s*:\s*$", ln):
            in_plugins = True
            in_disabled = False
            continue
        if in_plugins and re.match(r"^\S", ln):
            in_plugins = False
            in_disabled = False
        if in_plugins and re.match(r"^\s*disabled\s*:\s*$", ln):
            in_disabled = True
            continue
        if in_disabled:
            m2 = re.match(r"^\s*-\s*(.+?)\s*$", ln)
            if m2:
                disabled.append(m2.group(1).strip().strip("'\""))
            else:
                # end of list
                if ln.strip() and not ln.strip().startswith("#"):
                    in_disabled = False
    return disabled


def set_disabled_plugins(text: str, disabled: list[str]) -> str:
    obj = safe_load_yaml(text)
    if isinstance(obj, dict):
        plugins = obj.get("plugins")
        if not isinstance(plugins, dict):
            plugins = {}
            obj["plugins"] = plugins
        plugins["disabled"] = disabled
        dumped = safe_dump_yaml(obj)
        if isinstance(dumped, str):
            return dumped

    # Fallback: simple rewrite/add plugins.disabled as block list.
    # Remove existing plugins: block if present (very conservative)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\s*plugins\s*:\s*$", ln):
            # skip existing plugins block
            i += 1
            while i < len(lines) and not re.match(r"^\S", lines[i]):
                i += 1
            continue
        out.append(ln)
        i += 1

    if out and out[-1].strip() != "":
        out.append("")

    out.append("plugins:")
    out.append("  disabled:")
    for name in disabled:
        out.append(f"    - {name}")
    out.append("")
    return "\n".join(out)
