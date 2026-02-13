from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from .deps import Deps
from .model import RunnerError


@dataclass(frozen=True)
class PatchApplyResult:
    changed_paths: tuple[str, ...]


def _extract_changed_paths_from_unified(diff_text: str) -> list[str]:
    paths: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            # diff --git a/path b/path
            parts = line.split()
            if len(parts) >= 4:
                b = parts[3]
                if b.startswith("b/"):
                    p = b[2:]
                    if p and p not in paths:
                        paths.append(p)
    return paths


def _load_patches(patch_input: Path) -> list[tuple[str, str]]:
    """Return list of (name, unified_diff_text)."""
    if patch_input.suffix == ".zip":
        out: list[tuple[str, str]] = []
        with zipfile.ZipFile(patch_input, "r") as z:
            for n in sorted(z.namelist()):
                if not n.endswith(".patch"):
                    continue
                data = z.read(n).decode("utf-8")
                out.append((n, data))
        if not out:
            raise RunnerError(f"Patch zip contains no .patch files: {patch_input}")
        return out

    data = patch_input.read_text(encoding="utf-8")
    return [(patch_input.name, data)]


def apply_patch(target_root: Path, patch_input: Path, deps: Deps) -> PatchApplyResult:
    patches = _load_patches(patch_input)

    tmp_dir = target_root / ".am_patch_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    changed: list[str] = []
    for idx, (name, diff_text) in enumerate(patches):
        changed.extend([p for p in _extract_changed_paths_from_unified(diff_text) if p not in changed])

        pfile = tmp_dir / f"{idx:04d}_{Path(name).name}"
        pfile.write_text(diff_text, encoding="utf-8")

        res = deps.runner.run(["git", "apply", "--whitespace=nowarn", str(pfile)], cwd=target_root)
        if res.returncode != 0:
            raise RunnerError(f"git apply failed for {name}: {res.stderr.strip() or res.stdout.strip()}")

    # Best-effort cleanup.
    for p in tmp_dir.glob("*"):
        try:
            p.unlink()
        except Exception:
            pass
    try:
        tmp_dir.rmdir()
    except Exception:
        pass

    return PatchApplyResult(changed_paths=tuple(changed))
