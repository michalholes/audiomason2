from __future__ import annotations

import os
import sys

_ANSI_GREEN = "\x1b[32m"
_ANSI_RED = "\x1b[31m"
_ANSI_YELLOW = "\x1b[33m"
_ANSI_RESET = "\x1b[0m"


def stdout_color_enabled(mode: str) -> bool:
    """Return True if ANSI colors should be emitted to stdout.

    mode:
      - auto: enabled only when stdout is a TTY
      - always: always enabled
      - never: disabled

    Environment:
      - NO_COLOR: when set, disables color regardless of mode.
    """

    if os.getenv("NO_COLOR") is not None:
        return False

    m = str(mode or "auto").strip().lower()
    if m == "never":
        return False
    if m == "always":
        return True
    # auto
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def wrap_green(text: str, enabled: bool) -> str:
    return f"{_ANSI_GREEN}{text}{_ANSI_RESET}" if enabled else text


def wrap_red(text: str, enabled: bool) -> str:
    return f"{_ANSI_RED}{text}{_ANSI_RESET}" if enabled else text


def wrap_yellow(text: str, enabled: bool) -> str:
    return f"{_ANSI_YELLOW}{text}{_ANSI_RESET}" if enabled else text
