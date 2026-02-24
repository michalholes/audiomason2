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

from patchhub.app_api_amp import api_amp_schema
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


class TestAmpSchema(unittest.TestCase):
    def test_schema_contains_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "patches").mkdir(parents=True)
            (root / "scripts" / "am_patch").mkdir(parents=True)
            (root / "scripts" / "am_patch" / "am_patch.toml").write_text(
                'verbosity = "normal"\n', encoding="utf-8"
            )

            dummy = _Dummy(repo_root=root)
            status, data = api_amp_schema(dummy)
            self.assertEqual(status, 200)
            obj = json.loads(data.decode("utf-8"))
            self.assertTrue(obj.get("ok"))
            schema = obj.get("schema")
            self.assertIsInstance(schema, dict)
            fields = schema.get("fields")
            self.assertIsInstance(fields, list)

            by_key = {f.get("key"): f for f in fields if isinstance(f, dict)}
            self.assertIn("verbosity", by_key)
            self.assertIn("console_color", by_key)
            self.assertEqual(by_key["verbosity"].get("kind"), "enum")
