from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


def normalize_config_keys(raw: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(raw)

    if "log_level" in out and "verbosity" not in out:
        out["verbosity"] = out["log_level"]

    if "test_mode" not in out and "badguys_test_mode" in out:
        out["test_mode"] = out["badguys_test_mode"]

    return out


def import_legacy(submodule: str) -> ModuleType:
    repo_root = Path(__file__).resolve().parents[1]
    legacy_dir = repo_root / "scripts" / "am_patch"
    legacy_init = legacy_dir / "__init__.py"
    if not legacy_init.exists():
        raise ImportError(f"Legacy runner package not found: {legacy_init}")

    pkg_name = "_am_patch_legacy"
    if pkg_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            pkg_name,
            legacy_init,
            submodule_search_locations=[str(legacy_dir)],
        )
        if spec is None or spec.loader is None:
            raise ImportError("Cannot create legacy package spec")
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name] = pkg
        spec.loader.exec_module(pkg)

    return importlib.import_module(f"{pkg_name}.{submodule}")
