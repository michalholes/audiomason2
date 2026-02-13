from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


class CommandResult(Protocol):
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult: ...


class FileOps(Protocol):
    def copytree(self, src: Path, dst: Path) -> None: ...
    def rmtree(self, path: Path) -> None: ...
    def mkdir(self, path: Path) -> None: ...
    def exists(self, path: Path) -> bool: ...


class EventSink(Protocol):
    def emit(self, event: str) -> None: ...


@dataclass(frozen=True)
class Deps:
    runner: CommandRunner
    fs: FileOps
    events: EventSink


@dataclass
class SubprocessResult:
    returncode: int
    stdout: str
    stderr: str


class SubprocessRunner:
    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> SubprocessResult:
        p = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd is not None else None,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return SubprocessResult(returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)


class OSFileOps:
    def copytree(self, src: Path, dst: Path) -> None:
        shutil.copytree(src, dst, dirs_exist_ok=False)

    def rmtree(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=False)

    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def exists(self, path: Path) -> bool:
        return path.exists()


class ListEventSink:
    def __init__(self) -> None:
        self.events: list[str] = []

    def emit(self, event: str) -> None:
        self.events.append(event)


def default_deps() -> Deps:
    return Deps(runner=SubprocessRunner(), fs=OSFileOps(), events=ListEventSink())
