# badguys: make workspace dirty and fail scope
from pathlib import Path

FILES = [
    "badguys/tmp/dirty_workspace.txt",
]

# Baseline must be "base\n".
p = Path("badguys/tmp/dirty_workspace.txt")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("dirty\n", encoding="utf-8")

# Additionally touch an undeclared tracked file to force a scope failure.
Path("badguys/tmp/UNDECLARED_DIRTY.txt").write_text("dirty_undeclared\n", encoding="utf-8")
