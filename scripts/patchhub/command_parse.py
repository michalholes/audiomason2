from __future__ import annotations

import shlex
from dataclasses import dataclass

from .models import JobMode


class CommandParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedCommand:
    mode: JobMode
    issue_id: str
    commit_message: str
    patch_path: str
    canonical_argv: list[str]


def parse_runner_command(raw: str) -> ParsedCommand:
    raw = raw.strip()
    if not raw:
        raise CommandParseError("Empty command")

    try:
        argv = shlex.split(raw)
    except ValueError as e:
        raise CommandParseError(str(e)) from e

    if len(argv) < 3:
        raise CommandParseError("Command is too short")

    # Find scripts/am_patch.py in argv
    try:
        idx = argv.index("scripts/am_patch.py")
    except ValueError as e:
        raise CommandParseError("Missing scripts/am_patch.py") from e

    prefix = argv[: idx + 1]
    rest = argv[idx + 1 :]

    mode: JobMode = "patch"
    flag_f = "-f" in rest
    flag_w = "-w" in rest
    flag_l = "-l" in rest
    flag_count = int(flag_f) + int(flag_w) + int(flag_l)
    if flag_count > 1:
        raise CommandParseError("Conflicting finalize/rerun flags")

    if flag_f:
        mode = "finalize_live"
        rest = [a for a in rest if a != "-f"]
        if len(rest) != 1:
            raise CommandParseError("finalize_live requires exactly one MESSAGE argument")
        message = rest[0]
        if not message:
            raise CommandParseError("MESSAGE is empty")
        return ParsedCommand(
            mode=mode,
            issue_id="",
            commit_message=message,
            patch_path="",
            canonical_argv=prefix + ["-f", message],
        )

    if flag_w:
        mode = "finalize_workspace"
        rest = [a for a in rest if a != "-w"]
        if len(rest) != 1:
            raise CommandParseError("finalize_workspace requires exactly one ISSUE_ID argument")
        issue_id = rest[0]
        if not issue_id.isdigit():
            raise CommandParseError("ISSUE_ID must be digits")
        return ParsedCommand(
            mode=mode,
            issue_id=issue_id,
            commit_message="",
            patch_path="",
            canonical_argv=prefix + ["-w", issue_id],
        )

    if flag_l:
        mode = "rerun_latest"
        rest = [a for a in rest if a != "-l"]
        if len(rest) != 0:
            raise CommandParseError("rerun_latest must not include extra args")
        return ParsedCommand(
            mode=mode,
            issue_id="",
            commit_message="",
            patch_path="",
            canonical_argv=prefix + ["-l"],
        )

    if len(rest) != 3:
        raise CommandParseError('Expected: ISSUE_ID "commit message" PATCH')

    issue_id, commit_message, patch_path = rest
    if not issue_id.isdigit():
        raise CommandParseError("ISSUE_ID must be digits")
    if not commit_message:
        raise CommandParseError("Commit message is empty")
    if not patch_path:
        raise CommandParseError("PATCH is empty")

    canonical = prefix + [issue_id, commit_message, patch_path]
    return ParsedCommand(
        mode=mode,
        issue_id=issue_id,
        commit_message=commit_message,
        patch_path=patch_path,
        canonical_argv=canonical,
    )


def build_canonical_command(
    runner_prefix: list[str],
    mode: JobMode,
    issue_id: str,
    commit_message: str,
    patch_path: str,
) -> list[str]:
    if mode == "finalize_live":
        return runner_prefix + ["-f", commit_message]
    if mode == "finalize_workspace":
        return runner_prefix + ["-w", issue_id]
    if mode == "rerun_latest":
        return runner_prefix + ["-l"]
    if mode in ("patch", "repair"):
        return runner_prefix + [issue_id, commit_message, patch_path]
    raise CommandParseError(f"Unsupported mode: {mode}")
