import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

PATCH_PREFIX = "patches/per_file/"
PATCH_SUFFIX = ".patch"


def fail(code: str, detail: str) -> None:
    print("RESULT: FAIL")
    print(f"RULE {code}: FAIL - {detail}")
    raise SystemExit(1)


def read_zip(path: Path) -> tuple[list[str], dict[str, bytes]]:
    with ZipFile(path, "r") as zf:
        names = zf.namelist()
        items = {name: zf.read(name) for name in names if not name.endswith("/")}
    return names, items


def patch_paths(items: dict[str, bytes]) -> list[str]:
    paths = []
    for name in sorted(items):
        if not (name.startswith(PATCH_PREFIX) and name.endswith(PATCH_SUFFIX)):
            continue
        paths.append(name[len(PATCH_PREFIX) : -len(PATCH_SUFFIX)].replace("__", "/"))
    if not paths:
        fail("PATCH_LAYOUT", "no per-file patches found")
    return paths


def parse_freeze(text: str) -> list[str]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict) and isinstance(obj.get("files"), list):
        return sorted(str(item) for item in obj["files"])
    marker = "FILES MANIFEST"
    start = text.find(marker)
    if start == -1:
        fail("FREEZE", "missing FILES MANIFEST")
    block = text[start:].split("\n\n", 1)[0]
    files = []
    for line in block.splitlines()[1:]:
        stripped = line.strip()
        if stripped.startswith("-"):
            files.append(stripped[1:].strip())
    if not files:
        fail("FREEZE", "empty FILES MANIFEST")
    return sorted(files)


def extract_code_blocks(text: str) -> list[str]:
    return [
        match.group(1)
        for match in re.finditer(r"```[a-zA-Z0-9_-]*\n(.*?)```", text, flags=re.S)
    ]


def snapshot_tree(path: Path, root: Path) -> None:
    with ZipFile(path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/"):
                continue
            dst = root / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(zf.read(name))


def apply_patches(root: Path, items: dict[str, bytes]) -> None:
    for name, raw in items.items():
        if not name.startswith(PATCH_PREFIX):
            continue
        patch_path = root / ".pm_spec_validator" / Path(name).name
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_bytes(raw)
        proc = subprocess.run(
            ["git", "apply", "--check", str(patch_path)],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or name
            fail("GIT_APPLY", detail)
        proc = subprocess.run(
            ["git", "apply", str(patch_path)],
            cwd=root,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or name
            fail("GIT_APPLY", detail)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("issue_id")
    parser.add_argument("commit_message")
    parser.add_argument("patch")
    parser.add_argument("--workspace-snapshot", required=True)
    parser.add_argument("--freeze", required=True)
    return parser.parse_args(argv)


def main(argv: list[str]) -> None:
    args = parse_args(argv)
    freeze_text = Path(args.freeze).read_text(encoding="utf-8")
    allowed = parse_freeze(freeze_text)
    _names, items = read_zip(Path(args.patch))
    changed = patch_paths(items)
    if sorted(changed) != sorted(allowed):
        fail("SCOPE", f"expected={allowed}:actual={changed}")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        snapshot_tree(Path(args.workspace_snapshot), root)
        apply_patches(root, items)
        modified_texts = []
        for rel in changed:
            path = root / rel
            if path.exists():
                modified_texts.append(path.read_text(encoding="utf-8", errors="ignore"))
        code_blocks = [block for block in extract_code_blocks(freeze_text) if len(block) >= 40]
        for index, block in enumerate(code_blocks, start=1):
            if not any(block.strip() in text for text in modified_texts):
                fail("FREEZE_TEXT", f"code_block_{index}_not_found_in_outputs")
    print("RESULT: PASS")


if __name__ == "__main__":
    main(sys.argv[1:])
