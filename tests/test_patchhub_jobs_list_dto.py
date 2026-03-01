# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.models import JobRecord, job_to_list_item_json


class TestPatchhubJobsListDto(unittest.TestCase):
    def test_job_to_list_item_json_thin(self) -> None:
        j = JobRecord(
            job_id="J123",
            created_utc="2026-03-01T00:00:00Z",
            mode="patch",
            issue_id="703",
            commit_message="msg",
            patch_path="patches/x.zip",
            raw_command="python3 scripts/am_patch.py ...",
            canonical_command=["python3", "scripts/am_patch.py"],
            status="running",
            started_utc="2026-03-01T00:00:01Z",
            ended_utc=None,
            return_code=None,
            error=None,
            cancel_requested_utc="2026-03-01T00:00:02Z",
            cancel_ack_utc=None,
            cancel_source="socket",
        )

        dto = job_to_list_item_json(j)
        self.assertEqual(
            set(dto.keys()),
            {
                "job_id",
                "status",
                "created_utc",
                "started_utc",
                "ended_utc",
                "mode",
                "issue_id",
                "commit_message",
                "patch_path",
            },
        )
        self.assertEqual(dto["job_id"], "J123")
        self.assertEqual(dto["status"], "running")
        self.assertNotIn("raw_command", dto)
        self.assertNotIn("canonical_command", dto)
        self.assertNotIn("cancel_source", dto)

        # Must be JSON serializable (list endpoint payload)
        json.dumps(dto)
