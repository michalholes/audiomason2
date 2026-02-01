from __future__ import annotations

import os
import time
from typing import Any

_START = time.time()


def build_status() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "uptime_s": int(time.time() - _START),
    }
