from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(prog="am_patch_web")
    ap.add_argument(
        "--config",
        default="scripts/am_patch_web/am_patch_web.toml",
        help="Path to am_patch_web.toml",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    scripts_dir = repo_root / "scripts"
    sys.path.insert(0, str(scripts_dir))

    from am_patch_web.app import App
    from am_patch_web.config import load_config
    from am_patch_web.server import WebServer

    cfg_path = (repo_root / args.config).resolve()
    cfg = load_config(cfg_path)

    app = App(repo_root=repo_root, cfg=cfg)
    server = WebServer((cfg.server.host, cfg.server.port), app=app)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
