from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_repo_root_on_syspath() -> None:
    # When executed as: python3 plugins/web_interface/run.py
    # sys.path[0] is plugins/web_interface, so top-level "plugins" is not importable.
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8081)
    args = p.parse_args(argv)

    _ensure_repo_root_on_syspath()

    # Fast-fail on syntax errors in plugin package
    import compileall

    ok = compileall.compile_dir("plugins/web_interface", quiet=1)
    if not ok:
        return 2

    from plugins.web_interface.core import WebInterfacePlugin

    WebInterfacePlugin().run(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
