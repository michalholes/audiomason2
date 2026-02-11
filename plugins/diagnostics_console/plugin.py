"""diagnostics_console plugin.

Provides a CLI command `audiomason diag` that streams the central runtime
Diagnostics JSONL sink:

  <stage_dir>/diagnostics/diagnostics.jsonl

This plugin is CLI-only. It does not emit diagnostics itself; it reads the
existing sink.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from typing import Any

from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core.config import ConfigResolver
from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginError


@dataclass(frozen=True)
class _DiagArgs:
    subcommand: str
    follow: bool
    max_events: int | None


def _parse_diag_args(argv: list[str]) -> _DiagArgs:
    """Parse `audiomason diag` argv (excluding the command name itself)."""
    if not argv:
        argv = ["tail"]

    subcommand = argv[0]
    rest = argv[1:]

    follow = True
    max_events: int | None = None

    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--no-follow":
            follow = False
        elif a == "--max-events":
            if i + 1 >= len(rest):
                raise PluginError("--max-events requires a value")
            try:
                max_events = int(rest[i + 1])
            except ValueError as e:
                raise PluginError(f"Invalid --max-events: {rest[i + 1]!r}") from e
            if max_events <= 0:
                raise PluginError("--max-events must be > 0")
            i += 1
        elif a in ("-h", "--help"):
            raise PluginError("help")
        else:
            raise PluginError(f"Unknown argument: {a}")
        i += 1

    return _DiagArgs(subcommand=subcommand, follow=follow, max_events=max_events)


def _format_event_line(evt: dict[str, Any]) -> str:
    """Format a single diagnostics envelope into one compact line."""
    parts: list[str] = []

    ts = evt.get("timestamp")
    if isinstance(ts, str) and ts:
        parts.append(ts)

    event = evt.get("event")
    if isinstance(event, str) and event:
        parts.append(event)

    component = evt.get("component")
    if isinstance(component, str) and component:
        parts.append(component)

    operation = evt.get("operation")
    if isinstance(operation, str) and operation:
        parts.append(operation)

    data = evt.get("data")
    if isinstance(data, dict):
        job_id = data.get("job_id")
        if isinstance(job_id, str) and job_id:
            parts.append(f"job={job_id}")

        status = data.get("status")
        if isinstance(status, str) and status:
            parts.append(f"status={status}")

        err_type = data.get("error_type")
        err_msg = data.get("error_message")
        if isinstance(err_type, str) and err_type:
            if isinstance(err_msg, str) and err_msg:
                parts.append(f"err={err_type}: {err_msg}")
            else:
                parts.append(f"err={err_type}")
        elif isinstance(err_msg, str) and err_msg:
            parts.append(f"err={err_msg}")

    return " ".join(parts) if parts else "<empty event>"


def _cli_args_for_resolver_from_sysargv() -> dict[str, Any]:
    """Extract minimal CLI args needed for diagnostics resolver status.

    The core CLI host parses these flags too, but plugin commands are dispatched
    after the host has already consumed verbosity flags.

    This plugin only needs diagnostics.enabled for status output.
    """
    cli_args: dict[str, Any] = {}
    args = sys.argv[1:]
    if "--diagnostics" in args:
        cli_args.setdefault("diagnostics", {})["enabled"] = True
    if "--no-diagnostics" in args:
        cli_args.setdefault("diagnostics", {})["enabled"] = False
    return cli_args


class DiagnosticsConsolePlugin:
    """Plugin implementing ICLICommands for `audiomason diag`."""

    def get_cli_commands(self) -> dict[str, Any]:
        return {"diag": self._handle_diag}

    def _handle_diag(self, argv: list[str]) -> int:
        try:
            args = _parse_diag_args(argv)
        except PluginError as e:
            if str(e) == "help":
                self._print_help()
                return 0
            raise

        if args.subcommand == "tail":
            return self._cmd_tail(follow=args.follow, max_events=args.max_events)

        if args.subcommand == "status":
            return self._cmd_status()

        if args.subcommand == "on":
            cfg = ConfigService()
            cfg.set_value("diagnostics.enabled", True)
            print("diagnostics.enabled = true (source=user_config)")
            return 0

        if args.subcommand == "off":
            cfg = ConfigService()
            cfg.unset_value("diagnostics.enabled")
            print("diagnostics.enabled = false (source=default)")
            return 0

        raise PluginError(f"Unknown subcommand: {args.subcommand}")

    def _print_help(self) -> None:
        print("Usage:")
        print("  audiomason diag                Tail diagnostics sink (follow)")
        print("  audiomason diag tail           Tail diagnostics sink (follow)")
        print("  audiomason diag tail --no-follow [--max-events N]")
        print("  audiomason diag tail [--max-events N]")
        print("  audiomason diag status         Show effective diagnostics.enabled")
        print("  audiomason diag on             Enable diagnostics in USER config")
        print("  audiomason diag off            Disable diagnostics in USER config")

    def _cmd_status(self) -> int:
        cli_args = _cli_args_for_resolver_from_sysargv()
        resolver = ConfigResolver(cli_args=cli_args)
        try:
            val, src = resolver.resolve("diagnostics.enabled")
        except Exception:
            val, src = False, "default"

        enabled = bool(val)
        enabled_str = "true" if enabled else "false"
        print(f"diagnostics.enabled = {enabled_str} (source={src})")
        return 0

    def _cmd_tail(self, *, follow: bool, max_events: int | None) -> int:
        cli_args = _cli_args_for_resolver_from_sysargv()
        resolver = ConfigResolver(cli_args=cli_args)
        fs = FileService.from_resolver(resolver)

        rel_path = "diagnostics/diagnostics.jsonl"

        if not fs.exists(RootName.STAGE, rel_path):
            if not follow:
                print("no events")
                return 0

            last_notice = 0.0
            while not fs.exists(RootName.STAGE, rel_path):
                now = time.time()
                if now - last_notice >= 2.0:
                    print("waiting for diagnostics sink...")
                    last_notice = now
                time.sleep(0.2)

        printed = 0
        offset = 0

        while True:
            printed, offset = self._read_once(
                fs,
                rel_path,
                offset=offset,
                already_printed=printed,
                max_events=max_events,
            )

            if max_events is not None and printed >= max_events:
                return 0

            if not follow:
                return 0

            time.sleep(0.2)

    def _read_once(
        self,
        fs: FileService,
        rel_path: str,
        *,
        offset: int,
        already_printed: int,
        max_events: int | None,
    ) -> tuple[int, int]:
        printed = already_printed

        # Read full file and print new lines past offset. This is deterministic and
        # avoids keeping a file handle open across iterations.
        with fs.open_read(RootName.STAGE, rel_path) as f:
            data = f.read()

        if not isinstance(data, (bytes, bytearray)):
            raise PluginError("diagnostics sink read returned non-bytes")

        new_bytes = bytes(data)[offset:]
        if not new_bytes:
            return printed, offset

        # Update offset to end-of-file.
        new_offset = offset + len(new_bytes)

        for raw_line in new_bytes.splitlines():
            if max_events is not None and printed >= max_events:
                break

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                evt = json.loads(line)
            except Exception:
                print("WARN: invalid jsonl line")
                continue

            if not isinstance(evt, dict):
                print("WARN: invalid jsonl event")
                continue

            print(_format_event_line(evt))
            printed += 1

        return printed, new_offset
