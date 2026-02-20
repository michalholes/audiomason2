# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from am_patch_web.app import App


class TestApiParseCommand(unittest.TestCase):
    def test_parse_ok(self) -> None:
        app = App.__new__(App)
        raw = 'python3 scripts/am_patch.py 219 "x" patches/y.zip'
        status, body = App.api_parse_command(app, {"raw": raw})
        self.assertEqual(status, 200)
        obj = json.loads(body.decode("utf-8"))
        self.assertTrue(obj.get("ok"))
        self.assertEqual(obj["parsed"]["issue_id"], "219")
        self.assertEqual(obj["parsed"]["commit_message"], "x")
        self.assertEqual(obj["parsed"]["patch_path"], "patches/y.zip")
        argv = obj["canonical"]["argv"]
        self.assertIn("scripts/am_patch.py", argv)

    def test_parse_bad(self) -> None:
        app = App.__new__(App)
        status, body = App.api_parse_command(app, {"raw": "python3 x.py 1 a b"})
        self.assertEqual(status, 400)
        obj = json.loads(body.decode("utf-8"))
        self.assertFalse(obj.get("ok"))
