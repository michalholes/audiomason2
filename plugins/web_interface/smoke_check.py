#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path


def _repo_root() -> Path:
    # .../repo/plugins/web_interface/smoke_check.py -> repo root is 2 parents up
    return Path(__file__).resolve().parents[2]


def _patches_dir(repo_root: Path) -> Path:
    d = repo_root / "patches"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fetch(url: str, timeout_s: float) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "am-web-interface-smoke/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        status = int(getattr(resp, "status", 200))
        headers = {k.lower(): v for k, v in dict(resp.headers).items()}
        body = resp.read()
    return status, headers, body


def run_smoke(base_url: str, timeout_s: float, paths: Iterable[str]) -> dict:
    results = []
    started = time.time()

    for p in paths:
        url = base_url.rstrip("/") + p
        t0 = time.time()
        item = {"path": p, "url": url}
        try:
            status, headers, body = _fetch(url, timeout_s=timeout_s)
            item["status"] = status
            item["ms"] = int((time.time() - t0) * 1000)
            item["content_type"] = headers.get("content-type", "")
            preview = body[:200]
            try:
                item["preview"] = preview.decode("utf-8", errors="replace")
            except Exception:
                item["preview"] = repr(preview)
        except urllib.error.HTTPError as e:
            item["status"] = int(getattr(e, "code", 0) or 0)
            item["ms"] = int((time.time() - t0) * 1000)
            item["error"] = f"HTTPError: {e}"
        except Exception as e:
            item["status"] = 0
            item["ms"] = int((time.time() - t0) * 1000)
            item["error"] = f"{type(e).__name__}: {e}"
        results.append(item)

    return {
        "base_url": base_url,
        "started_at_epoch": started,
        "duration_ms": int((time.time() - started) * 1000),
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke-check web_interface pages and API endpoints.")
    ap.add_argument(
        "--base-url", default="http://127.0.0.1:8081", help="Base URL, e.g. http://127.0.0.1:8081"
    )
    ap.add_argument("--timeout", type=float, default=3.0, help="Per-request timeout seconds")
    ap.add_argument(
        "--out",
        default="",
        help="Output file path (default: patches/web_interface_smoke_report.json)",
    )
    args = ap.parse_args()

    # UI pages (SPA paths) + API endpoints used by the UI
    paths = [
        "/ui/assets/app.js",
        "/ui/assets/app.css",
        "/",
        "/dashboard",
        "/plugins",
        "/stage",
        "/wizards",
        "/logs",
        "/config",
        "/ui-config",
        "/api/ui/nav",
        "/api/ui/pages",
        "/api/ui/page/dashboard",
        "/api/status",
        "/api/am/config",
        "/api/plugins",
        "/api/stage",
        "/api/wizards",
        "/api/logs/tail?lines=5",
    ]

    report = run_smoke(args.base_url, timeout_s=args.timeout, paths=paths)

    repo = _repo_root()
    if args.out:
        out_path = Path(args.out).expanduser()
    else:
        out_path = _patches_dir(repo) / "web_interface_smoke_report.json"

    out_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
