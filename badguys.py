#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent
    s = str(repo_root)
    if sys.path and sys.path[0] == s:
        pass
    elif s in sys.path:
        sys.path.remove(s)
        sys.path.insert(0, s)
    else:
        sys.path.insert(0, s)

    from badguys.run_suite import main as suite_main

    return int(suite_main(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
