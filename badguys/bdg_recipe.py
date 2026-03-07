from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import tomllib


_BASE_CFG_KEYS = ("suite", "lock", "guard", "filters", "runner")


def _config_relpath(config_path: Path | str) -> str:
    path = Path(config_path)
    return path.as_posix()


@lru_cache(maxsize=None)
def _load_raw(repo_root_str: str, config_relpath: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str)
    path = repo_root / Path(config_relpath)
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _raw(*, repo_root: Path, config_path: Path | str) -> dict[str, Any]:
    return _load_raw(str(repo_root), _config_relpath(config_path))


def _copy_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return deepcopy(value)


def ensure_allowed_keys(*, table: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(set(table) - allowed)
    if extra:
        joined = ", ".join(extra)
        raise SystemExit(f"FAIL: bdg recipe: {label} has unknown keys: {joined}")


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


def base_cfg_sections(*, repo_root: Path, config_path: Path | str) -> dict[str, Any]:
    raw = _raw(repo_root=repo_root, config_path=config_path)
    return {key: _copy_dict(raw.get(key, {})) for key in _BASE_CFG_KEYS}


def subject_relpaths(
    *,
    repo_root: Path,
    config_path: Path | str,
    test_id: str,
) -> dict[str, str]:
    raw = _raw(repo_root=repo_root, config_path=config_path)
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
        ensure_allowed_keys(
            table=item,
            allowed={"relpath"},
            label=f"subjects.tests.{test_id}.{name}",
        )
        relpath = item.get("relpath")
        if not isinstance(relpath, str) or not relpath:
            raise SystemExit(
                f"FAIL: bdg recipe: subjects.tests.{test_id}.{name}.relpath "
                "must be a string"
            )
        out[str(name)] = relpath
    return out


def asset_recipe(
    *,
    repo_root: Path,
    config_path: Path | str,
    test_id: str,
    asset_id: str,
) -> dict[str, Any]:
    recipe = _test_recipe(_raw(repo_root=repo_root, config_path=config_path), test_id)
    assets = recipe.get("assets", {})
    if not isinstance(assets, dict):
        return {}
    out = _copy_dict(assets.get(asset_id, {}))
    if not isinstance(out, dict):
        raise SystemExit(
            f"FAIL: bdg recipe: recipes.tests.{test_id}.assets.{asset_id} must be a table"
        )
    return out


def entry_recipe(
    *,
    repo_root: Path,
    config_path: Path | str,
    test_id: str,
    asset_id: str,
    entry_id: str,
) -> dict[str, Any]:
    asset = asset_recipe(
        repo_root=repo_root,
        config_path=config_path,
        test_id=test_id,
        asset_id=asset_id,
    )
    entries = asset.get("entries", {})
    if not isinstance(entries, dict):
        return {}
    out = _copy_dict(entries.get(entry_id, {}))
    if not isinstance(out, dict):
        raise SystemExit(
            "FAIL: bdg recipe: recipes.tests."
            f"{test_id}.assets.{asset_id}.entries.{entry_id} must be a table"
        )
    return out


def step_recipe(
    *,
    repo_root: Path,
    config_path: Path | str,
    test_id: str,
    step_index: int,
) -> dict[str, Any]:
    recipe = _test_recipe(_raw(repo_root=repo_root, config_path=config_path), test_id)
    steps = recipe.get("steps", {})
    if not isinstance(steps, dict):
        return {}
    if str(step_index) in steps:
        out = _copy_dict(steps[str(step_index)])
    else:
        out = _copy_dict(steps.get(step_index, {}))
    if not isinstance(out, dict):
        raise SystemExit(
            f"FAIL: bdg recipe: recipes.tests.{test_id}.steps.{step_index} must be a table"
        )
    return out
