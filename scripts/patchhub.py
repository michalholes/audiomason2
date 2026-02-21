"""PatchHub entry point.

Contract (HARD):
- Before changing PatchHub behavior, read scripts/patchhub_specification.md.
- Any behavior change (UI/API/validation/defaults) requires:
  - updating scripts/patchhub_specification.md
  - bumping PatchHub runtime version in scripts/patchhub/patchhub.toml ([meta].version)
  - SemVer rules: MAJOR.MINOR.PATCH

Version is NOT hardcoded in code. The source of truth is patchhub.toml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="patchhub",
        description="PatchHub (AM Patch Web UI)",
    )
    ap.add_argument(
        "--config",
        default="scripts/patchhub/patchhub.toml",
        help="Path to patchhub.toml",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    scripts_dir = repo_root / "scripts"
    sys.path.insert(0, str(scripts_dir))

    from patchhub.app import App
    from patchhub.config import load_config
    from patchhub.server import WebServer

    cfg_path = (repo_root / args.config).resolve()
    cfg = load_config(cfg_path)

    app = App(repo_root=repo_root, cfg=cfg)
    server = WebServer((cfg.server.host, cfg.server.port), app=app)
    host = cfg.server.host
    port = cfg.server.port
    print(f"WEB: listening on http://{host}:{port}")
    if host == "0.0.0.0":
        print(f"WEB: local access http://127.0.0.1:{port}")
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
