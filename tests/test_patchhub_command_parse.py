# ruff: noqa: E402
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.command_parse import CommandParseError, parse_runner_command


class TestCommandParse(unittest.TestCase):
    def test_parse_patch(self) -> None:
        c = 'python3 scripts/am_patch.py 1000 "Issue #1000: test" patches/x.zip'
        p = parse_runner_command(c)
        self.assertEqual(p.mode, "patch")
        self.assertEqual(p.issue_id, "1000")
        self.assertEqual(p.patch_path, "patches/x.zip")

    def test_parse_finalize(self) -> None:
        c = "python3 scripts/am_patch.py -f"
        p = parse_runner_command(c)
        self.assertEqual(p.mode, "finalize_live")

    def test_missing_runner(self) -> None:
        with self.assertRaises(CommandParseError):
            parse_runner_command("python3 x.py 1 a b")
