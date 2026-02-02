#!/usr/bin/env python3
"""
Extract files that have mypy errors into patches/mypyfails/ preserving paths.

Usage:
  python3 extract_mypyfails.py /path/to/mypy.log
  python3 extract_mypyfails.py /path/to/mypy.log --repo /path/to/repo --out patches/mypyfails

Assumptions:
- mypy output lines look like: "relative/or/absolute/path.py:LINE: error: ..."
- Copies only files that exist on disk.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path
from typing import Iterable


MYPY_ERROR_RE = re.compile(
    r"""^
    (?P<path>.+?)
    :
    (?P<line>\d+)
    (?:
        :(?P<col>\d+)
    )?
    :
    \s+
    error:
    """,
    re.VERBOSE,
)


def iter_error_files(log_text: str) -> Iterable[str]:
    seen: set[str] = set()
    for raw_line in log_text.splitlines():
        line = raw_line.rstrip("\n")
        m = MYPY_ERROR_RE.match(line)
        if not m:
            continue
        p = m.group("path").strip()
        if p and p not in seen:
            seen.add(p)
            yield p


def as_repo_relative(path_str: str, repo_root: Path) -> Path | None:
    p = Path(path_str)

    # If absolute, try to make it relative to repo_root.
    if p.is_absolute():
        try:
            return p.relative_to(repo_root)
        except ValueError:
            return None

    # If relative, treat as relative to repo_root.
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", type=Path, help="Path to mypy log file (text).")
    ap.add_argument("--repo", type=Path, default=Path.cwd(), help="Repo root (default: cwd).")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("patches/mypyfails"),
        help="Output dir (default: patches/mypyfails).",
    )
    args = ap.parse_args()

    log_path: Path = args.log
    repo_root: Path = args.repo.resolve()
    out_dir: Path = (repo_root / args.out).resolve()

    if not log_path.exists():
        raise SystemExit(f"Log not found: {log_path}")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")

    error_paths = list(iter_error_files(log_text))
    if not error_paths:
        print("No mypy error file paths detected in log.")
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    skipped: list[str] = []

    for path_str in error_paths:
        rel = as_repo_relative(path_str, repo_root)
        if rel is None:
            skipped.append(f"{path_str} (not under repo root)")
            continue

        src = (repo_root / rel).resolve()
        # Prevent path traversal / weirdness.
        try:
            src.relative_to(repo_root)
        except ValueError:
            skipped.append(f"{path_str} (resolves outside repo root)")
            continue

        if not src.exists() or not src.is_file():
            skipped.append(f"{path_str} (missing on disk)")
            continue

        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    # Write list file
    list_file = out_dir / "_mypy_files.txt"
    content = "\n".join(str(p) for p in copied)
    if copied:
        content += "\n"
    list_file.write_text(content, encoding="utf-8")

    print(f"Repo root: {repo_root}")
    print(f"Log:       {log_path}")
    print(f"Out:       {out_dir}")
    print(f"Found:     {len(error_paths)} file(s) with mypy errors in log")
    print(f"Copied:    {len(copied)} file(s)")
    if skipped:
        print(f"Skipped:   {len(skipped)} item(s)")
        # Print a small tail so it doesn't spam.
        for s in skipped[:20]:
            print(f"  - {s}")
        if len(skipped) > 20:
            print(f"  ... ({len(skipped) - 20} more)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

