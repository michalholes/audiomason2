# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.app_api_amp import api_amp_config_get, api_amp_config_post
from patchhub.fs_jail import FsJail


class _Dummy:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.cfg = SimpleNamespace(
            runner=SimpleNamespace(runner_config_toml="scripts/am_patch/am_patch.toml")
        )
        self.jail = FsJail(
            repo_root=repo_root,
            patches_root_rel="patches",
            crud_allowlist=[""],
            allow_crud=True,
        )


class TestAmpConfigRoundtrip(unittest.TestCase):
    def test_get_validate_save_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "patches").mkdir(parents=True)
            (root / "scripts" / "am_patch").mkdir(parents=True)

            cfg_path = root / "scripts" / "am_patch" / "am_patch.toml"
            cfg_path.write_text(
                'verbosity = "normal"\n\n[gates]\ngate_monolith_mode = "strict"\n',
                encoding="utf-8",
            )

            dummy = _Dummy(repo_root=root)

            st1, data1 = api_amp_config_get(dummy)
            self.assertEqual(st1, 200)
            obj1 = json.loads(data1.decode("utf-8"))
            self.assertTrue(obj1.get("ok"))
            self.assertEqual(obj1.get("values", {}).get("verbosity"), "normal")

            # Dry-run validation (no write).
            st2, data2 = api_amp_config_post(
                dummy, {"values": {"verbosity": "quiet"}, "dry_run": True}
            )
            self.assertEqual(st2, 200)
            obj2 = json.loads(data2.decode("utf-8"))
            self.assertTrue(obj2.get("ok"))
            self.assertTrue(obj2.get("dry_run"))

            # Dry-run returns typed values as-if the update was written.
            self.assertEqual(obj2.get("values", {}).get("verbosity"), "quiet")

            # No write happened.
            self.assertIn('verbosity = "normal"', cfg_path.read_text(encoding="utf-8"))

            st2b, data2b = api_amp_config_get(dummy)
            self.assertEqual(st2b, 200)
            obj2b = json.loads(data2b.decode("utf-8"))
            self.assertTrue(obj2b.get("ok"))
            self.assertEqual(obj2b.get("values", {}).get("verbosity"), "normal")

            # Save.
            st3, data3 = api_amp_config_post(
                dummy, {"values": {"verbosity": "quiet"}, "dry_run": False}
            )
            self.assertEqual(st3, 200)
            obj3 = json.loads(data3.decode("utf-8"))
            self.assertTrue(obj3.get("ok"))
            self.assertFalse(obj3.get("dry_run"))

            st4, data4 = api_amp_config_get(dummy)
            obj4 = json.loads(data4.decode("utf-8"))
            self.assertTrue(obj4.get("ok"))
            self.assertEqual(obj4.get("values", {}).get("verbosity"), "quiet")
