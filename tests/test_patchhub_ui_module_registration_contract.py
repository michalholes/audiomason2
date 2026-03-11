from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _loaded_modules() -> list[tuple[str, str]]:
    src = _read("scripts/patchhub/static/app.js")
    matches = re.findall(r'loadScript\("([^"]+)",\s*"([^"]+)"\)', src)
    return [(path, name) for path, name in matches if name not in {"progress", "live"}]


def test_each_loaded_patchhub_module_registers_exact_loader_name() -> None:
    loaded = _loaded_modules()
    assert loaded
    for path, name in loaded:
        rel = "scripts/patchhub/static/" + path.split("/")[-1]
        src = _read(rel)
        assert f'PH.register("{name}"' in src


def test_wire_init_is_started_via_dispatcher_capability() -> None:
    src = _read("scripts/patchhub/static/app.js")
    assert 'PH.call("startAppWireInit")' in src
    assert "PH_APP_START" not in src


def test_zip_subset_registration_uses_loader_name_not_legacy_alias() -> None:
    src = _read("scripts/patchhub/static/app_part_zip_subset.js")
    assert 'PH.register("app_part_zip_subset"' in src
    assert 'PH.register("zip_subset"' not in src


def test_wire_init_uses_dispatcher_for_amp_settings_and_snapshot_modules() -> None:
    src = _read("scripts/patchhub/static/app_part_wire_init.js")
    assert 'phCall("initAmpSettings")' in src
    assert 'phCall("refreshOverviewSnapshot", { mode: "user" })' in src
    assert 'phCall("ensureSnapshotEvents")' in src
    assert 'phCall("stopSnapshotEvents")' in src
    assert "window).AmpSettings" not in src
