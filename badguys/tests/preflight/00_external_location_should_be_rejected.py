# This script is intentionally located under badguys/tests (not under patches/).
# Runner preflight must reject patch scripts outside patches/ with PREFLIGHT:PATCH_PATH.

FILES = [
    "badguys/tmp/external_reject.txt",
]

from pathlib import Path

p = Path("badguys/tmp/external_reject.txt")
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text("x\n", encoding="utf-8")
