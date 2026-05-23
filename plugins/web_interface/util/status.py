from __future__ import annotations

import os
import time

_START = time.time()


def build_status() -> dict[str, object]:
    return {
        "pid": os.getpid(),
        "uptime_s": int(time.time() - _START),
    }
