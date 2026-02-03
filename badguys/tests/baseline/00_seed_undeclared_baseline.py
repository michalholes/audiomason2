# badguys: seed baseline for undeclared_* tests (workspace-only; no live git)
from pathlib import Path

FILES = [
    "badguys/tmp/undeclared.txt",
    "badguys/tmp/.seed_undeclared_marker.txt",
]

Path("badguys/tmp").mkdir(parents=True, exist_ok=True)

Path("badguys/tmp/undeclared.txt").write_text("base\n", encoding="utf-8")

marker = Path("badguys/tmp/.seed_undeclared_marker.txt")
cur = marker.read_text(encoding="utf-8") if marker.exists() else ""
marker.write_text("A\n" if cur != "A\n" else "B\n", encoding="utf-8")
