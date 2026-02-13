"""Syslog persistence service.

This module provides a thin wrapper over the file_io capability.
All filesystem operations MUST go through FileService.

The syslog file is stored under the STAGE root, configured by
logging.system_log_path (relative).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from audiomason.core.log_bus import LogRecord
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName


@dataclass(frozen=True)
class SyslogConfig:
    enabled: bool
    filename: str
    disk_format: str  # jsonl | plain
    cli_default_command: str  # tail | status | cat
    cli_default_follow: bool


class SyslogService:
    """Append/read/tail/follow syslog file under the file_io STAGE root."""

    def __init__(self, fs: FileService, *, filename: str, disk_format: str) -> None:
        self._fs = fs
        self._filename = filename
        self._disk_format = disk_format

    @property
    def filename(self) -> str:
        return self._filename

    @property
    def disk_format(self) -> str:
        return self._disk_format

    def exists(self) -> bool:
        return self._fs.exists(RootName.STAGE, self._filename)

    def append_record(self, record: LogRecord) -> None:
        line = self._encode_record(record)
        with self._fs.open_append(RootName.STAGE, self._filename, mkdir_parents=True) as f:
            f.write(line)

    def read_all_raw(self) -> str:
        with self._fs.open_read(RootName.STAGE, self._filename) as f:
            data = f.read()
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("syslog read returned non-bytes")
        return bytes(data).decode("utf-8", errors="replace")

    def tail_lines_raw(self, n: int) -> list[str]:
        if n <= 0:
            return []

        # Read at most N lines from the end by tailing bytes with a conservative cap.
        # This is a best-effort tail that avoids reading full files for very large logs.
        max_bytes = max(4096, n * 512)
        raw = self._fs.tail_bytes(RootName.STAGE, self._filename, max_bytes=max_bytes)
        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-n:]

    def follow_lines_raw(self, *, poll_interval_s: float = 0.2) -> Any:
        """Yield new raw lines as they are appended.

        Implementation reads the full file on each poll and yields only new lines
        past the last byte offset.
        """
        offset = 0
        while True:
            with self._fs.open_read(RootName.STAGE, self._filename) as f:
                data = f.read()

            if not isinstance(data, (bytes, bytearray)):
                raise TypeError("syslog read returned non-bytes")

            b = bytes(data)
            new_bytes = b[offset:]
            if new_bytes:
                offset += len(new_bytes)
                for raw_line in new_bytes.splitlines():
                    line = raw_line.decode("utf-8", errors="replace")
                    if line.strip() == "":
                        continue
                    yield line

            time.sleep(poll_interval_s)

    def human_render_lines(self, raw_lines: list[str]) -> list[str]:
        if self._disk_format == "plain":
            return raw_lines

        # jsonl -> compact human rendering
        out: list[str] = []
        for line in raw_lines:
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                out.append(s)
                continue

            if not isinstance(obj, dict):
                out.append(s)
                continue

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

            out.append(" ".join(parts) if parts else s)

        return out

    def _encode_record(self, record: LogRecord) -> bytes:
        if self._disk_format == "plain":
            plain = record.plain if record.plain is not None else ""
            return (plain + "\n").encode("utf-8")

        # jsonl
        msg = record.plain if record.plain is not None else ""
        obj: dict[str, Any] = {
            "level": record.level_name,
            "logger": record.logger_name,
            "message": msg,
            "ts": None,
        }
        line = json.dumps(obj, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        return (line + "\n").encode("utf-8")
