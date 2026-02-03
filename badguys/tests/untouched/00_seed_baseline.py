# badguys: seed baseline files for declared-but-untouched tests
from pathlib import Path

FILES = [
    "badguys/tmp/untouched_a.txt",
    "badguys/tmp/untouched_b.txt",
]

pa = Path("badguys/tmp/untouched_a.txt")
pb = Path("badguys/tmp/untouched_b.txt")
pa.parent.mkdir(parents=True, exist_ok=True)

# Seed deterministic baseline. This step is used to keep the workspace between subsequent steps.
pa.write_text("base\n", encoding="utf-8")
pb.write_text("base\n", encoding="utf-8")
