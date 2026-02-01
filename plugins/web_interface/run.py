from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
import importlib.util
import compileall


def _load_web_interface_plugin():
    """Load WebInterfacePlugin from plugin.py without relying on package imports."""
    here = Path(__file__).resolve().parent
    plugin_py = here / "plugin.py"
    spec = importlib.util.spec_from_file_location("web_interface_plugin", plugin_py)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load spec for {plugin_py}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["web_interface_plugin"] = module
    spec.loader.exec_module(module)
    return module.WebInterfacePlugin


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AudioMason web_interface (standalone)")
    p.add_argument("--host", default=os.environ.get("WEB_INTERFACE_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("WEB_INTERFACE_PORT", "8081")))
    return p.parse_args()


def main() -> int:
    here = Path(__file__).resolve().parent

    # Fast fail on syntax errors before starting the server.
    if not compileall.compile_file(str(here / "plugin.py"), quiet=1):
        raise SystemExit("web_interface: plugin.py failed to compile (syntax error)")

    WebInterfacePlugin = _load_web_interface_plugin()
    args = _parse_args()
    WebInterfacePlugin().run(host=str(args.host), port=int(args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
