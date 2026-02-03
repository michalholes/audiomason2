# badguys: undeclared-path contract
from pathlib import Path

# Declare one file, and touch both:
# - declared file (must be changed each run to satisfy declared_untouched_fail)
# - an outside file (should fail without -a, pass with -a)
FILES = [
    "badguys/tmp/declared.txt",
]

decl = Path("badguys/tmp/declared.txt")
decl.parent.mkdir(parents=True, exist_ok=True)
cur_decl = decl.read_text(encoding="utf-8") if decl.exists() else ""
next_decl = "declared-A\n" if cur_decl != "declared-A\n" else "declared-B\n"
decl.write_text(next_decl, encoding="utf-8")

outside = Path("badguys/tmp/undeclared.txt")
outside.parent.mkdir(parents=True, exist_ok=True)
cur_out = outside.read_text(encoding="utf-8") if outside.exists() else ""
next_out = "outside-A\n" if cur_out != "outside-A\n" else "outside-B\n"
outside.write_text(next_out, encoding="utf-8")
