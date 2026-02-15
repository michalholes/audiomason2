# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import unittest

from am_patch_web.indexing import parse_run_result_from_log_text


class TestIndexParseResult(unittest.TestCase):
    def test_success(self) -> None:
        res, line = parse_run_result_from_log_text("x\nRESULT: SUCCESS\n")
        self.assertEqual(res, "success")
        self.assertEqual(line, "RESULT: SUCCESS")

    def test_unknown(self) -> None:
        res, line = parse_run_result_from_log_text("nope\n")
        self.assertEqual(res, "unknown")
        self.assertIsNone(line)
