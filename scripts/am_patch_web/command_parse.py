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
    if "-f" in rest:
        mode = "finalize_live"
        rest = [a for a in rest if a != "-f"]
    if "-w" in rest:
        mode = "finalize_workspace"
        rest = [a for a in rest if a != "-w"]
    if "-l" in rest:
        mode = "rerun_latest"
        rest = [a for a in rest if a != "-l"]

    if mode in ("finalize_live", "finalize_workspace", "rerun_latest"):
        if len(rest) != 0:
            raise CommandParseError("Finalize/rerun commands must not include extra args")
        return ParsedCommand(
            mode=mode,
            issue_id="",
            commit_message="",
            patch_path="",
            canonical_argv=prefix + ["-f"]
            if mode == "finalize_live"
            else prefix + ["-w"]
            if mode == "finalize_workspace"
            else prefix + ["-l"],
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
        return runner_prefix + ["-f"]
    if mode == "finalize_workspace":
        return runner_prefix + ["-w"]
    if mode == "rerun_latest":
        return runner_prefix + ["-l"]
    if mode in ("patch", "repair"):
        return runner_prefix + [issue_id, commit_message, patch_path]
    raise CommandParseError(f"Unsupported mode: {mode}")
