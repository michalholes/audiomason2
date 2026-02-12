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
    mode: str


def _parse_diag_args(argv: list[str]) -> _DiagArgs:
    """Parse `audiomason diag` argv (excluding the command name itself)."""
    if not argv:
        argv = ["tail"]

    # Help must be handled even when passed as the first arg (no subcommand).
    if argv[0] in ("-h", "--help"):
        return _DiagArgs(subcommand="help", follow=True, max_events=None, mode="events")

    # Allow: `audiomason diag --mode log` (no explicit subcommand -> tail)
    if argv[0].startswith("-"):
        argv = ["tail", *argv]

    subcommand = argv[0]
    rest = argv[1:]

    follow = True
    max_events: int | None = None
    mode = "events"

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
        elif a == "--mode":
            if i + 1 >= len(rest):
                raise PluginError("--mode requires a value")
            mode = rest[i + 1]
            if mode not in ("events", "log", "both"):
                raise PluginError("Invalid --mode (allowed: events, log, both)")
            i += 1
        elif a in ("-h", "--help"):
            raise PluginError("help")
        else:
            raise PluginError(f"Unknown argument: {a}")
        i += 1

    return _DiagArgs(
        subcommand=subcommand,
        follow=follow,
        max_events=max_events,
        mode=mode,
    )


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

        if args.subcommand == "help":
            self._print_help()
            return 0

        if args.subcommand == "tail":
            return self._cmd_tail(
                follow=args.follow,
                max_events=args.max_events,
                mode=args.mode,
            )

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
        print("  audiomason diag [--mode events|log|both]                Tail (follow)")
        print("  audiomason diag tail [--mode events|log|both]           Tail (follow)")
        print("  audiomason diag tail --no-follow [--max-events N] [--mode events|log|both]")
        print("  audiomason diag tail [--max-events N] [--mode events|log|both]")
        print("  audiomason diag status                                 Show diagnostics.enabled")
        print("  audiomason diag on                                     Enable diagnostics (USER)")
        print(
            "  audiomason diag off                                    Disable diagnostics (default)"
        )

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

    def _cmd_tail(self, *, follow: bool, max_events: int | None, mode: str) -> int:
        cli_args = _cli_args_for_resolver_from_sysargv()
        resolver = ConfigResolver(cli_args=cli_args)
        fs = FileService.from_resolver(resolver)

        if mode == "events":
            return self._tail_events(fs, resolver, follow=follow, max_events=max_events)

        if mode == "log":
            return self._tail_log(fs, resolver, follow=follow)

        if mode == "both":
            return self._tail_both(fs, resolver, follow=follow, max_events=max_events)

        raise PluginError(f"Unknown mode: {mode!r}")

    def _tail_events(
        self,
        fs: FileService,
        resolver: ConfigResolver,
        *,
        follow: bool,
        max_events: int | None,
    ) -> int:
        rel_path = "diagnostics/diagnostics.jsonl"

        repeat_wait = self._try_resolve_bool(
            resolver, "diagnostics.console.wait_status_repeat", default=False
        )

        if not fs.exists(RootName.STAGE, rel_path):
            if not follow:
                print("no events")
                return 0

            printed_wait = False
            last_notice = 0.0

            while not fs.exists(RootName.STAGE, rel_path):
                if not printed_wait:
                    print("waiting for diagnostics sink...")
                    printed_wait = True
                    last_notice = time.time()

                if repeat_wait:
                    now = time.time()
                    if now - last_notice >= 2.0:
                        print("waiting for diagnostics sink...")
                        last_notice = now

                time.sleep(0.2)

        printed = 0
        offset = 0

        while True:
            printed, offset = self._read_events_once(
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

    def _tail_log(
        self,
        fs: FileService,
        resolver: ConfigResolver,
        *,
        follow: bool,
    ) -> int:
        filename = self._try_resolve_str(
            resolver, "plugins.syslog.filename", default="logs/system.log"
        )
        disk_format = self._try_resolve_str(
            resolver,
            "plugins.syslog.disk_format",
            default="jsonl",
        )

        if disk_format not in ("plain", "jsonl"):
            disk_format = "jsonl"

        if not fs.exists(RootName.CONFIG, filename):
            if not follow:
                print("missing syslog file")
                return 2
            while not fs.exists(RootName.CONFIG, filename):
                time.sleep(0.2)

        offset = 0
        while True:
            offset = self._read_syslog_once(
                fs,
                filename,
                offset=offset,
                disk_format=disk_format,
            )
            if not follow:
                return 0
            time.sleep(0.2)

    def _tail_both(
        self,
        fs: FileService,
        resolver: ConfigResolver,
        *,
        follow: bool,
        max_events: int | None,
    ) -> int:
        # Offsets are tracked independently. Loop reads events then logs on each tick.
        rel_path = "diagnostics/diagnostics.jsonl"

        filename = self._try_resolve_str(
            resolver, "plugins.syslog.filename", default="logs/system.log"
        )
        disk_format = self._try_resolve_str(
            resolver,
            "plugins.syslog.disk_format",
            default="jsonl",
        )
        if disk_format not in ("plain", "jsonl"):
            disk_format = "jsonl"

        repeat_wait = self._try_resolve_bool(
            resolver, "diagnostics.console.wait_status_repeat", default=False
        )

        printed = 0
        events_offset = 0
        log_offset = 0

        # For follow=false, attempt one read pass and exit (with non-zero
        # if log missing).
        if not follow:
            if fs.exists(RootName.STAGE, rel_path):
                printed, events_offset = self._read_events_once(
                    fs,
                    rel_path,
                    offset=events_offset,
                    already_printed=printed,
                    max_events=max_events,
                )
            else:
                print("no events")

            if not fs.exists(RootName.CONFIG, filename):
                print("missing syslog file")
                return 2

            log_offset = self._read_syslog_once(
                fs, filename, offset=log_offset, disk_format=disk_format
            )
            return 0

        # follow=true: wait for events sink with optional status printing;
        # log waits silently.
        printed_wait = False
        last_notice = 0.0

        while True:
            if fs.exists(RootName.STAGE, rel_path):
                printed, events_offset = self._read_events_once(
                    fs,
                    rel_path,
                    offset=events_offset,
                    already_printed=printed,
                    max_events=max_events,
                )
            else:
                if not printed_wait:
                    print("waiting for diagnostics sink...")
                    printed_wait = True
                    last_notice = time.time()
                if repeat_wait:
                    now = time.time()
                    if now - last_notice >= 2.0:
                        print("waiting for diagnostics sink...")
                        last_notice = now

            if fs.exists(RootName.CONFIG, filename):
                log_offset = self._read_syslog_once(
                    fs, filename, offset=log_offset, disk_format=disk_format
                )

            if max_events is not None and printed >= max_events:
                return 0

            time.sleep(0.2)
        printed = 0
        offset = 0

        while True:
            printed, offset = self._read_events_once(
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

    def _try_resolve_bool(
        self,
        resolver: ConfigResolver,
        key: str,
        *,
        default: bool,
    ) -> bool:
        try:
            v, _src = resolver.resolve(key)
        except Exception:
            return default
        if isinstance(v, bool):
            return v
        return bool(v)

    def _try_resolve_str(
        self,
        resolver: ConfigResolver,
        key: str,
        *,
        default: str,
    ) -> str:
        try:
            v, _src = resolver.resolve(key)
        except Exception:
            return default
        return v if isinstance(v, str) else default

    def _read_syslog_once(
        self,
        fs: FileService,
        filename: str,
        *,
        offset: int,
        disk_format: str,
    ) -> int:
        with fs.open_read(RootName.CONFIG, filename) as f:
            data = f.read()

        if not isinstance(data, (bytes, bytearray)):
            raise PluginError("syslog read returned non-bytes")

        b = bytes(data)
        new_bytes = b[offset:]
        if not new_bytes:
            return offset

        new_offset = offset + len(new_bytes)

        for raw_line in new_bytes.splitlines():
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            rendered = self._render_syslog_line(line, disk_format=disk_format)
            print(f"LOG: {rendered}")

        return new_offset

    def _render_syslog_line(self, line: str, *, disk_format: str) -> str:
        if disk_format == "plain":
            return line

        s = line.strip()
        if not s:
            return ""

        try:
            obj = json.loads(s)
        except Exception:
            return s

        if not isinstance(obj, dict):
            return s

        level = obj.get("level")
        logger = obj.get("logger")
        msg = obj.get("message")

        parts: list[str] = []
        if isinstance(level, str) and level:
            parts.append(level)
        if isinstance(logger, str) and logger:
            parts.append(str(logger) + ":")
        if isinstance(msg, str) and msg:
            parts.append(msg)

        return " ".join(parts) if parts else s

    def _read_events_once(
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
