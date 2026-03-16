from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from am_patch.errors import RunnerError
from am_patch.manifest import load_files
from am_patch.patch_archive_select import select_latest_issue_patch
from am_patch.patch_exec import precheck_patch_script
from am_patch.patch_select import PatchSelectError, choose_default_patch_input, decide_unified_mode
from am_patch.repo_root import is_under
from am_patch.root_model import resolve_patch_root


@dataclass(frozen=True)
class PatchPlan:
    patch_script: Path
    unified_mode: bool
    files_declared: list[str]


def _resolve_patch_input_path(
    *,
    cli: Any,
    issue_id: int,
    patch_root: Path,
) -> Path:
    patch_script: Path | None = None

    if getattr(cli, "load_latest_patch", None):
        hint_name = Path(cli.patch_script).name if cli.patch_script else None
        patch_script = select_latest_issue_patch(
            patch_dir=patch_root,
            issue_id=str(issue_id),
            hint_name=hint_name,
        )
    elif cli.patch_script:
        raw = Path(cli.patch_script)
        if raw.is_absolute():
            patch_script = raw
        else:
            cand_cwd = (Path.cwd() / raw).resolve()
            cand_patchdir = (patch_root / raw).resolve()
            if cand_cwd.exists() and is_under(cand_cwd, patch_root):
                patch_script = cand_cwd
            elif cand_patchdir.exists():
                patch_script = cand_patchdir
            else:
                raise RunnerError(
                    "PREFLIGHT",
                    "MANIFEST",
                    f"patch script not found (tried: {cand_cwd} and {cand_patchdir})",
                )
    else:
        try:
            patch_script = choose_default_patch_input(patch_root, issue_id)
        except PatchSelectError as e:
            raise RunnerError("PREFLIGHT", "MANIFEST", str(e)) from e

    assert patch_script is not None

    if not patch_script.exists():
        raise RunnerError("PREFLIGHT", "MANIFEST", f"patch script not found: {patch_script}")

    if not is_under(patch_script, patch_root):
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_PATH",
            f"patch script must be under {patch_root} (got {patch_script})",
        )
    return patch_script


def _read_patch_carried_target_selector(patch_script: Path) -> str | None:
    if patch_script.suffix.lower() != ".zip":
        return None
    try:
        with zipfile.ZipFile(patch_script, "r") as zf:
            matches = [
                info.filename
                for info in zf.infolist()
                if not info.is_dir() and PurePosixPath(info.filename).parts == ("target.txt",)
            ]
            if not matches:
                return None
            if len(matches) != 1:
                raise RunnerError(
                    "PREFLIGHT",
                    "PATCH_PATH",
                    "zip patch input contains multiple root-level target.txt entries",
                )
            raw = zf.read(matches[0])
    except zipfile.BadZipFile as exc:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_PATH",
            f"invalid zip file: {patch_script} ({exc})",
        ) from exc
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_PATH",
            "zip patch input target.txt must be ASCII-only",
        ) from exc
    if "\r" in text:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_PATH",
            "zip patch input target.txt must use LF newlines",
        )
    selector = text[:-1] if text.endswith("\n") else text
    if not selector or "\n" in selector:
        raise RunnerError(
            "PREFLIGHT",
            "PATCH_PATH",
            "zip patch input target.txt must contain exactly one non-empty line",
        )
    return selector


def _has_explicit_cli_target(policy: Any) -> bool:
    for key in ("active_target_repo_root", "repo_root"):
        if getattr(policy, "_src", {}).get(key) != "cli":
            continue
        return True
    return False


def apply_patch_carried_target_selector_for_startup(
    *,
    cli: Any,
    policy: Any,
    issue_id: int,
    runner_root: Path,
) -> None:
    if _has_explicit_cli_target(policy):
        return
    patch_root = resolve_patch_root(policy, runner_root=runner_root)
    patch_script = _resolve_patch_input_path(cli=cli, issue_id=issue_id, patch_root=patch_root)
    selector = _read_patch_carried_target_selector(patch_script)
    if selector is None:
        return
    policy.active_target_repo_root = selector
    policy._src["active_target_repo_root"] = "patch-carried"


def resolve_patch_plan(
    *,
    logger: Any,
    cli: Any,
    policy: Any,
    issue_id: int,
    repo_root: Path,
    patch_root: Path,
) -> PatchPlan:
    patch_script = _resolve_patch_input_path(
        cli=cli,
        issue_id=issue_id,
        patch_root=patch_root,
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
