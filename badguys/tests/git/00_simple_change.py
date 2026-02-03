# badguys: simple passing change (used for branch enforcement steps)
from pathlib import Path

FILES = [
    "badguys/tmp/simple_change.txt",
]

p = Path("badguys/tmp/simple_change.txt")
p.parent.mkdir(parents=True, exist_ok=True)

cur = p.read_text(encoding="utf-8") if p.exists() else ""
new = "A\n" if cur != "A\n" else "B\n"
p.write_text(new, encoding="utf-8")
