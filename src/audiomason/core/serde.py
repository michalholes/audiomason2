from __future__ import annotations

import json
from typing import TextIO

import yaml


def json_loads_object(text: str) -> object:
    return json.loads(text)  # type: ignore[misc]


def json_dumps_text(
    value: object,
    *,
    ensure_ascii: bool = True,
    separators: tuple[str, str] | None = None,
    sort_keys: bool = False,
    indent: int | None = None,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=ensure_ascii,
        separators=separators,
        sort_keys=sort_keys,
        indent=indent,
    )


def yaml_safe_load_stream(stream: TextIO) -> object:
    return yaml.safe_load(stream)  # type: ignore[misc]


def yaml_safe_load_text(text: str) -> object:
    return yaml.safe_load(text)  # type: ignore[misc]
