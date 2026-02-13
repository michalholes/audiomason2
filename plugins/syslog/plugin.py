"""syslog plugin.

This plugin subscribes to the Core LogBus and persists log records via the
file_io capability (STAGE root). It also provides a CLI command:

  audiomason syslog

See docs/specification.md for configuration and behavior.
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from typing import Any

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.errors import PluginError
from audiomason.core.events import get_event_bus
from audiomason.core.log_bus import LogRecord, get_log_bus
from audiomason.core.logging import get_logger
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from .service import SyslogConfig, SyslogService

_LOG = get_logger(__name__)

_COMPONENT = "syslog"

_ALLOWED_FORMATS = {"jsonl", "plain"}
_ALLOWED_DEFAULT_CMDS = {"tail", "status", "cat"}


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    """Emit a runtime diagnostic event via the authoritative entrypoint.

    Fail-safe: must never raise.
    """
    try:
        env = build_envelope(event=event, component=_COMPONENT, operation=operation, data=data)
        get_event_bus().publish(event, env)
    except Exception as e:
        _LOG.warning(f"diagnostic emission failed: {type(e).__name__}: {e}")


@dataclass(frozen=True)
class _TailArgs:
    lines: int
    follow: bool
    raw: bool


def _parse_syslog_argv(argv: list[str], cfg: SyslogConfig) -> tuple[str, list[str]]:
    """Return (subcommand, rest_argv)."""
    if not argv:
        return cfg.cli_default_command, []

    if argv[0] in ("-h", "--help"):
        return "help", []

    return argv[0], argv[1:]


def _parse_tail_args(argv: list[str], cfg: SyslogConfig) -> _TailArgs:
    lines = 50
    raw = False

    follow = cfg.cli_default_follow
    explicit_follow: bool | None = None

    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            raise PluginError("help")
        if a == "--raw":
            raw = True
        elif a == "--lines":
            if i + 1 >= len(argv):
                raise PluginError("--lines requires a value")
            try:
                lines = int(argv[i + 1])
            except ValueError as e:
                raise PluginError(f"Invalid --lines: {argv[i + 1]!r}") from e
            if lines <= 0:
                raise PluginError("--lines must be > 0")
            i += 1
        elif a == "--follow":
            explicit_follow = True
        elif a == "--no-follow":
            explicit_follow = False
        else:
            raise PluginError(f"Unknown argument: {a}")
        i += 1

    if explicit_follow is not None:
        follow = explicit_follow

    return _TailArgs(lines=lines, follow=follow, raw=raw)


class SyslogPlugin:
    """syslog plugin implementing ICLICommands and LogBus subscription."""

    def __init__(self) -> None:
        self._resolver = ConfigResolver()
        self._fs = FileService.from_resolver(self._resolver)
        self._cfg = self._resolve_config(self._resolver)

        self._service: SyslogService | None = None
        self._subscribed = False
        self._write_failures = 0

        _emit_diag(
            "START",
            operation="plugin_init",
            data={
                "enabled": self._cfg.enabled,
                "filename": self._cfg.filename,
                "disk_format": self._cfg.disk_format,
            },
        )

        if not self._cfg.enabled:
            _emit_diag(
                "END",
                operation="plugin_init",
                data={"status": "succeeded", "subscribed": False},
            )
            return

        if self._cfg.disk_format not in _ALLOWED_FORMATS:
            _LOG.warning(
                "syslog disabled: invalid disk_format="
                f"{self._cfg.disk_format!r} (allowed: jsonl, plain)"
            )
            _emit_diag(
                "FAIL",
                operation="plugin_init",
                data={
                    "status": "failed",
                    "error_type": "ConfigError",
                    "error_message": f"invalid disk_format: {self._cfg.disk_format!r}",
                },
            )
            self._cfg = SyslogConfig(
                enabled=False,
                filename=self._cfg.filename,
                disk_format=self._cfg.disk_format,
                cli_default_command=self._cfg.cli_default_command,
                cli_default_follow=self._cfg.cli_default_follow,
            )
            return

        if not self._cfg.filename or self._cfg.filename.strip() == "":
            _LOG.warning("syslog disabled: empty filename")
            _emit_diag(
                "FAIL",
                operation="plugin_init",
                data={
                    "status": "failed",
                    "error_type": "ConfigError",
                    "error_message": "empty filename",
                },
            )
            self._cfg = SyslogConfig(
                enabled=False,
                filename=self._cfg.filename,
                disk_format=self._cfg.disk_format,
                cli_default_command=self._cfg.cli_default_command,
                cli_default_follow=self._cfg.cli_default_follow,
            )
            return

        # Validate and preflight the configured path deterministically.
        filename = self._cfg.filename.strip()

        # Absolute paths are forbidden: syslog must be under STAGE root.
        if filename.startswith("/"):
            msg = (
                "absolute paths not allowed for logging.system_log_path: "
                f"{filename!r}. Use a relative path under the stage root (e.g. 'logs/system.log')."
            )
            _LOG.error(msg)
            print(msg, file=sys.stderr)
            _emit_diag(
                "FAIL",
                operation="plugin_init",
                data={
                    "status": "failed",
                    "error_type": "ConfigError",
                    "error_message": msg,
                },
            )
            self._cfg = SyslogConfig(
                enabled=False,
                filename=filename,
                disk_format=self._cfg.disk_format,
                cli_default_command=self._cfg.cli_default_command,
                cli_default_follow=self._cfg.cli_default_follow,
            )
            return

        self._cfg = SyslogConfig(
            enabled=self._cfg.enabled,
            filename=filename,
            disk_format=self._cfg.disk_format,
            cli_default_command=self._cfg.cli_default_command,
            cli_default_follow=self._cfg.cli_default_follow,
        )

        # Preflight: ensure the file is writable and within roots (creates file if missing).
        try:
            with self._fs.open_append(RootName.STAGE, filename, mkdir_parents=True):
                pass
        except Exception as e:
            msg = (
                "syslog disabled: logging.system_log_path is not writable or is outside roots: "
                f"{filename!r} ({type(e).__name__}: {e})"
            )
            _LOG.error(msg)
            print(msg, file=sys.stderr)
            _emit_diag(
                "FAIL",
                operation="plugin_init",
                data={
                    "status": "failed",
                    "error_type": "ConfigError",
                    "error_message": msg,
                },
            )
            self._cfg = SyslogConfig(
                enabled=False,
                filename=filename,
                disk_format=self._cfg.disk_format,
                cli_default_command=self._cfg.cli_default_command,
                cli_default_follow=self._cfg.cli_default_follow,
            )
            return

        self._service = SyslogService(
            self._fs, filename=self._cfg.filename, disk_format=self._cfg.disk_format
        )

        try:
            get_log_bus().subscribe_all(self._on_log_record)
            self._subscribed = True
        except Exception as e:
            _emit_diag(
                "FAIL",
                operation="plugin_init",
                data={
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            raise

        _emit_diag(
            "END",
            operation="plugin_init",
            data={"status": "succeeded", "subscribed": True},
        )

    def get_cli_commands(self) -> dict[str, Any]:
        return {"syslog": self._handle_syslog}

    def _resolve_config(self, resolver: ConfigResolver) -> SyslogConfig:
        # Detect plugin namespace presence.
        plugin_ns_present = False
        try:
            v, _src = resolver.resolve("plugins.syslog")
            if isinstance(v, dict):
                plugin_ns_present = True
        except Exception:
            plugin_ns_present = False

        if plugin_ns_present:
            enabled = self._try_resolve_bool(resolver, "plugins.syslog.enabled", default=False)
            disk_format = self._try_resolve_str(
                resolver, "plugins.syslog.disk_format", default="jsonl"
            )
            cli_default_command = self._try_resolve_str(
                resolver, "plugins.syslog.cli_default_command", default="tail"
            )
            cli_default_follow = self._try_resolve_bool(
                resolver, "plugins.syslog.cli_default_follow", default=True
            )

            # Single source of truth: logging.system_log_path.
            system_log_path = self._try_resolve_str(resolver, "logging.system_log_path", default="")
            legacy_filename = self._try_resolve_str(resolver, "plugins.syslog.filename", default="")

            if system_log_path:
                filename = system_log_path
                # Deprecated: keep deterministic behavior, but warn when mismatch is detected.
                if legacy_filename and legacy_filename != system_log_path:
                    _LOG.warning(
                        "plugins.syslog.filename is deprecated and ignored because "
                        "logging.system_log_path is set"
                    )
                    _emit_diag(
                        "FAIL",
                        operation="config",
                        data={
                            "status": "failed",
                            "error_type": "ConfigError",
                            "error_message": (
                                "plugins.syslog.filename is deprecated; use logging.system_log_path"
                            ),
                        },
                    )
            else:
                filename = legacy_filename or "logs/system.log"
                if legacy_filename:
                    _LOG.warning(
                        "plugins.syslog.filename is deprecated; use logging.system_log_path"
                    )

        else:
            enabled = self._try_resolve_bool(resolver, "logging.system_log_enabled", default=False)

            filename = self._try_resolve_str(resolver, "logging.system_log_path", default="")
            if not filename:
                # Legacy alias name: logging.system_log_filename.
                filename = self._try_resolve_str(
                    resolver, "logging.system_log_filename", default=""
                )
            if not filename:
                filename = "logs/system.log"

            disk_format = self._try_resolve_str(
                resolver, "logging.system_log_format", default="jsonl"
            )
            cli_default_command = "tail"
            cli_default_follow = True

        if cli_default_command not in _ALLOWED_DEFAULT_CMDS:
            cli_default_command = "tail"

        return SyslogConfig(
            enabled=bool(enabled),
            filename=str(filename),
            disk_format=str(disk_format),
            cli_default_command=str(cli_default_command),
            cli_default_follow=bool(cli_default_follow),
        )

    @staticmethod
    def _try_resolve_bool(resolver: ConfigResolver, key: str, *, default: bool) -> bool:
        try:
            v, _src = resolver.resolve(key)
        except Exception:
            return default
        return bool(v)

    @staticmethod
    def _try_resolve_str(resolver: ConfigResolver, key: str, *, default: str) -> str:
        try:
            v, _src = resolver.resolve(key)
        except Exception:
            return default
        if v is None:
            return default
        return str(v)

    def _on_log_record(self, record: LogRecord) -> None:
        if self._service is None:
            return

        try:
            self._service.append_record(record)
            self._write_failures = 0
        except Exception as e:
            self._write_failures += 1

            if self._write_failures == 1:
                _emit_diag(
                    "FAIL",
                    operation="write",
                    data={
                        "status": "failed",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )

            if self._write_failures >= 3:
                # Disable: unsubscribe and stop writing.
                with contextlib.suppress(Exception):
                    get_log_bus().unsubscribe_all(self._on_log_record)

                self._service = None
                self._subscribed = False

                _LOG.warning("syslog disabled due to repeated write failures")
                _emit_diag(
                    "FAIL",
                    operation="write",
                    data={
                        "status": "failed",
                        "error_type": "WriteError",
                        "error_message": "syslog disabled due to repeated write failures",
                    },
                )

    def _handle_syslog(self, argv: list[str]) -> int:
        subcmd, rest = _parse_syslog_argv(argv, self._cfg)

        if subcmd == "help":
            self._print_help()
            return 0

        if subcmd == "status":
            return self._cmd_status(rest)

        if subcmd == "cat":
            return self._cmd_cat(rest)

        if subcmd == "tail":
            return self._cmd_tail(rest)

        raise PluginError(f"Unknown subcommand: {subcmd}")

    def _print_help(self) -> None:
        print("Usage:")
        print("  audiomason syslog                Default command (from config)")
        print("  audiomason syslog status         Show resolved syslog configuration")
        print("  audiomason syslog cat [--raw]    Print syslog contents")
        print("  audiomason syslog tail [--lines N] [--follow|--no-follow] [--raw]")
        print("")
        print("Notes:")
        print(
            "  - Log file path comes from logging.system_log_path and is relative to "
            "the file_io STAGE root."
        )
        print("  - tail follow mode is quiet when no new data arrives.")

    def _cmd_status(self, _argv: list[str]) -> int:
        _emit_diag("START", operation="cli_status", data={"cmd": "status"})
        try:
            svc = SyslogService(
                self._fs, filename=self._cfg.filename, disk_format=self._cfg.disk_format
            )
            exists = svc.exists()
            print(f"enabled = {'true' if self._cfg.enabled else 'false'}")
            print("root = stage")
            print("path_key = logging.system_log_path")
            print(f"filename = {self._cfg.filename}")
            print(f"disk_format = {self._cfg.disk_format}")
            print(f"file_exists = {'true' if exists else 'false'}")
            _emit_diag("END", operation="cli_status", data={"status": "succeeded"})
            return 0
        except Exception as e:
            _emit_diag(
                "FAIL",
                operation="cli_status",
                data={
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            raise

    def _cmd_cat(self, argv: list[str]) -> int:
        raw = False
        for a in argv:
            if a in ("-h", "--help"):
                print("Usage: audiomason syslog cat [--raw]")
                return 0
            if a == "--raw":
                raw = True
            else:
                raise PluginError(f"Unknown argument: {a}")

        _emit_diag("START", operation="cli_cat", data={"cmd": "cat", "raw": raw})

        svc = SyslogService(
            self._fs, filename=self._cfg.filename, disk_format=self._cfg.disk_format
        )
        if not svc.exists():
            msg = "syslog file does not exist"
            print(msg)
            _emit_diag(
                "FAIL",
                operation="cli_cat",
                data={"status": "failed", "error_type": "FileNotFound", "error_message": msg},
            )
            return 1

        try:
            text = svc.read_all_raw()
            if raw or self._cfg.disk_format == "plain":
                sys.stdout.write(text)
                if text and not text.endswith("\n"):
                    sys.stdout.write("\n")
            else:
                lines = svc.human_render_lines(text.splitlines())
                for line in lines:
                    print(line)
            _emit_diag("END", operation="cli_cat", data={"status": "succeeded"})
            return 0
        except Exception as e:
            _emit_diag(
                "FAIL",
                operation="cli_cat",
                data={
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            raise

    def _cmd_tail(self, argv: list[str]) -> int:
        svc = SyslogService(
            self._fs, filename=self._cfg.filename, disk_format=self._cfg.disk_format
        )

        try:
            args = _parse_tail_args(argv, self._cfg)
        except PluginError as e:
            if str(e) == "help":
                print("Usage: audiomason syslog tail [--lines N] [--follow|--no-follow] [--raw]")
                return 0
            raise

        _emit_diag(
            "START",
            operation="cli_tail",
            data={"cmd": "tail", "lines": args.lines, "follow": args.follow, "raw": args.raw},
        )

        if not svc.exists():
            msg = "syslog file does not exist"
            print(msg)
            _emit_diag(
                "FAIL",
                operation="cli_tail",
                data={"status": "failed", "error_type": "FileNotFound", "error_message": msg},
            )
            return 1

        try:
            raw_lines = svc.tail_lines_raw(args.lines)
            out_lines = raw_lines if args.raw else svc.human_render_lines(raw_lines)
            for line in out_lines:
                print(line)

            if not args.follow:
                _emit_diag("END", operation="cli_tail", data={"status": "succeeded"})
                return 0

            for line in svc.follow_lines_raw():
                out = line if args.raw else "".join(svc.human_render_lines([line]))
                if out.strip() == "":
                    continue
                print(out)

        except KeyboardInterrupt:
            _emit_diag(
                "END",
                operation="cli_tail",
                data={"status": "succeeded", "stopped": "keyboard_interrupt"},
            )
            return 0
        except Exception as e:
            _emit_diag(
                "FAIL",
                operation="cli_tail",
                data={
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            raise

        return 0
