# ruff: noqa: E402
from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.app_api_jobs import api_jobs_cancel, api_jobs_hard_stop
from patchhub.asgi.async_app_core import AsyncAppCore
from patchhub.config import load_config


class _QueueFalse:
    async def cancel(self, job_id: str) -> bool:
        del job_id
        return False

    async def hard_stop(self, job_id: str) -> bool:
        del job_id
        return False


@dataclass
class _LegacySelf:
    queue: Any


def _load_repo_cfg() -> Any:
    return load_config(
        Path(__file__).resolve().parents[1] / "scripts" / "patchhub" / "patchhub.toml"
    )


def test_legacy_api_jobs_cancel_returns_409_without_unawaited_warning() -> None:
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        status, raw = api_jobs_cancel(_LegacySelf(queue=_QueueFalse()), "job-800")
    payload = json.loads(raw.decode("utf-8"))
    assert status == 409
    assert payload["error"] == "Cannot cancel"
    assert not any("was never awaited" in str(item.message) for item in seen)


def test_legacy_api_jobs_hard_stop_returns_409_without_unawaited_warning() -> None:
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        status, raw = api_jobs_hard_stop(_LegacySelf(queue=_QueueFalse()), "job-801")
    payload = json.loads(raw.decode("utf-8"))
    assert status == 409
    assert payload["error"] == "Cannot hard stop"
    assert not any("was never awaited" in str(item.message) for item in seen)


def test_async_app_core_wires_terminate_grace_from_config(tmp_path: Path) -> None:
    cfg = _load_repo_cfg()
    core = AsyncAppCore(repo_root=tmp_path, cfg=cfg)
    assert core.queue._terminate_grace_s == cfg.runner.terminate_grace_s
