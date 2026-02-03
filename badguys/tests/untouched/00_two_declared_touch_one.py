# badguys: declared-but-untouched contract
from pathlib import Path

FILES = [
    "badguys/tmp/untouched_a.txt",
    "badguys/tmp/untouched_b.txt",
]

# Baseline in repo for both files must be "base\n".
# This patch must make a real change, while leaving one declared file untouched.
p = Path("badguys/tmp/untouched_a.txt")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("touched\n", encoding="utf-8")

# untouched_b.txt remains declared but untouched; without -t runner should fail SCOPE.
