from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import tomllib


_CONFIG_PATH = Path("badguys/config.toml")
_BASE_CFG_KEYS = ("suite", "lock", "guard", "filters", "runner")


@lru_cache(maxsize=None)
def _load_raw(repo_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str)
    path = repo_root / _CONFIG_PATH
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _copy_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return deepcopy(value)


def _tests_table(raw: dict[str, Any], section_name: str) -> dict[str, Any]:
    section = raw.get(section_name, {})
    if not isinstance(section, dict):
        return {}
    tests = section.get("tests", {})
    if not isinstance(tests, dict):
        return {}
    return tests


def _test_recipe(raw: dict[str, Any], test_id: str) -> dict[str, Any]:
    return _copy_dict(_tests_table(raw, "recipes").get(test_id, {}))


def base_cfg_sections(*, repo_root: Path) -> dict[str, Any]:
    raw = _load_raw(str(repo_root))
    return {key: _copy_dict(raw.get(key, {})) for key in _BASE_CFG_KEYS}


def subject_relpaths(*, repo_root: Path, test_id: str) -> dict[str, str]:
    raw = _load_raw(str(repo_root))
    tests = _tests_table(raw, "subjects")
    table = tests.get(test_id, {})
    if not isinstance(table, dict):
        return {}
    out: dict[str, str] = {}
    for name, item in table.items():
        if not isinstance(item, dict):
            raise SystemExit(
                f"FAIL: bdg recipe: subjects.tests.{test_id}.{name} must be a table"
            )
        relpath = item.get("relpath")
        if not isinstance(relpath, str) or not relpath:
            raise SystemExit(
                f"FAIL: bdg recipe: subjects.tests.{test_id}.{name}.relpath must be a string"
            )
        out[str(name)] = relpath
    return out


def asset_recipe(*, repo_root: Path, test_id: str, asset_id: str) -> dict[str, Any]:
    recipe = _test_recipe(_load_raw(str(repo_root)), test_id)
    assets = recipe.get("assets", {})
    if not isinstance(assets, dict):
        return {}
    return _copy_dict(assets.get(asset_id, {}))


def entry_recipe(
    *,
    repo_root: Path,
    test_id: str,
    asset_id: str,
    entry_id: str,
) -> dict[str, Any]:
    asset = asset_recipe(repo_root=repo_root, test_id=test_id, asset_id=asset_id)
    entries = asset.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    return _copy_dict(entries.get(entry_id, {}))


def step_recipe(*, repo_root: Path, test_id: str, step_index: int) -> dict[str, Any]:
    recipe = _test_recipe(_load_raw(str(repo_root)), test_id)
    steps = recipe.get("steps", {})
    if not isinstance(steps, dict):
        return {}
    if str(step_index) in steps:
        return _copy_dict(steps[str(step_index)])
    return _copy_dict(steps.get(step_index, {}))
