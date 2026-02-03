# badguys: after soft reset, workspace must be clean and this patch must pass
from pathlib import Path

FILES = [
    "badguys/tmp/after_soft_reset.txt",
]

expected = "base\n"

decl = Path("badguys/tmp/dirty_workspace.txt").read_text(encoding="utf-8")
undecl = Path("badguys/tmp/UNDECLARED_DIRTY.txt").read_text(encoding="utf-8")
if decl != expected or undecl != expected:
    raise SystemExit(
        "soft reset did not restore baseline: "
        f"dirty_workspace={decl!r} undeclared_dirty={undecl!r}"
    )

p = Path("badguys/tmp/after_soft_reset.txt")
p.parent.mkdir(parents=True, exist_ok=True)
cur = p.read_text(encoding="utf-8") if p.exists() else ""
new = "A\n" if cur != "A\n" else "B\n"
p.write_text(new, encoding="utf-8")
