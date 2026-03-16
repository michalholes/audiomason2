from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from am_patch.errors import RunnerError
from am_patch.manifest import load_files
from am_patch.patch_archive_select import select_latest_issue_patch
from am_patch.patch_exec import precheck_patch_script
from am_patch.patch_select import PatchSelectError, choose_default_patch_input, decide_unified_mode
from am_patch.repo_root import is_under


@dataclass(frozen=True)
class PatchPlan:
    patch_script: Path
    unified_mode: bool
    files_declared: list[str]


def resolve_patch_script_path(
    *,
    cli: Any,
    issue_id: int,
    patch_root: Path,
    require_exists: bool,
) -> Path:
    patch_script: Path | None = None

    if getattr(cli, "load_latest_patch", None):
        hint_name = Path(cli.patch_script).name if cli.patch_script else None
        try:
            patch_script = select_latest_issue_patch(
                patch_dir=patch_root,
                issue_id=str(issue_id),
                hint_name=hint_name,
            )
        except FileNotFoundError:
            if require_exists:
                raise
            patch_script = choose_default_patch_input(patch_root, issue_id)
    elif cli.patch_script:
        raw = Path(cli.patch_script)
        if raw.is_absolute():
            patch_script = raw.resolve()
        else:
            # Accept either:
            #  - a path relative to CWD (e.g. patches/issue_999.py), OR
            #  - a bare filename resolved under patch_dir (e.g. issue_999.py).
            cand_cwd = (Path.cwd() / raw).resolve()
            cand_patchdir = (patch_root / raw).resolve()
            if cand_cwd.exists() and is_under(cand_cwd, patch_root):
                patch_script = cand_cwd
            elif cand_patchdir.exists():
                patch_script = cand_patchdir
            elif require_exists:
                raise RunnerError(
                    "PREFLIGHT",
                    "MANIFEST",
                    f"patch script not found (tried: {cand_cwd} and {cand_patchdir})",
                )
            elif is_under(cand_cwd, patch_root):
                patch_script = cand_cwd
            else:
                patch_script = cand_patchdir
    else:
        try:
            patch_script = choose_default_patch_input(patch_root, issue_id)
        except PatchSelectError as e:
            raise RunnerError("PREFLIGHT", "MANIFEST", str(e)) from e

    assert patch_script is not None

    if require_exists and not patch_script.exists():
        raise RunnerError("PREFLIGHT", "MANIFEST", f"patch script not found: {patch_script}")

    if require_exists and not is_under(patch_script, patch_root):
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_PATH",
            f"patch script must be under {patch_root} (got {patch_script})",
        )

    return patch_script


def read_patch_carried_target(patch_script: Path) -> str | None:
    patch_script = patch_script.resolve()
    if patch_script.suffix != ".zip" or not patch_script.exists() or not patch_script.is_file():
        return None
    try:
        with zipfile.ZipFile(patch_script, "r") as zf:
            names = {name for name in zf.namelist() if not name.endswith("/")}
            if "target.txt" not in names:
                return None
            if not any(name.endswith(".patch") for name in names):
                return None
            data = zf.read("target.txt")
    except zipfile.BadZipFile:
        return None

    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_TARGET",
            f"target.txt must be ASCII-only: {patch_script}",
        ) from exc

    lines = text.splitlines()
    if not lines or len(lines) != 1:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_TARGET",
            f"target.txt must contain exactly one non-empty line: {patch_script}",
        )
    value = lines[0].strip()
    if not value:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_TARGET",
            f"target.txt must contain exactly one non-empty line: {patch_script}",
        )
    return value


def resolve_patch_plan(
    *,
    logger: Any,
    cli: Any,
    policy: Any,
    issue_id: int,
    repo_root: Path,
    patch_root: Path,
) -> PatchPlan:
    patch_script = resolve_patch_script_path(
        cli=cli,
        issue_id=issue_id,
        patch_root=patch_root,
        require_exists=True,
    )

    try:
        unified_mode = decide_unified_mode(
            patch_script,
            explicit_unified=bool(getattr(policy, "unified_patch", False)),
        )
    except PatchSelectError as e:
        raise RunnerError("PREFLIGHT", "PATCH_PATH", str(e)) from e

    if not unified_mode:
        precheck_patch_script(patch_script, ascii_only=policy.ascii_only_patch)

    files_declared: list[str] = [] if unified_mode else load_files(patch_script)

    return PatchPlan(
        patch_script=patch_script,
        unified_mode=unified_mode,
        files_declared=files_declared,
    )
