from __future__ import annotations

from pathlib import Path


def append_jsonl_line(jsonl_path: Path, line: str) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    data = line
    if not data.endswith("\n"):
        data += "\n"
    with jsonl_path.open("ab") as fp:
        fp.write(data.encode("utf-8", errors="replace"))
        fp.flush()
