from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class RunnerConfig:
    command: list[str]
    default_verbosity: str
    queue_enabled: bool
    runner_config_toml: str


@dataclass(frozen=True)
class PathsConfig:
    patches_root: str
    upload_dir: str
    allow_crud: bool
    crud_allowlist: list[str]


@dataclass(frozen=True)
class UploadConfig:
    max_bytes: int
    allowed_extensions: list[str]
    ascii_only_names: bool


@dataclass(frozen=True)
class IssueConfig:
    default_regex: str
    allocation_start: int
    allocation_max: int


@dataclass(frozen=True)
class IndexingConfig:
    log_filename_regex: str
    stats_windows_days: list[int]


@dataclass(frozen=True)
class UiConfig:
    base_font_px: int
    drop_overlay_enabled: bool


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    runner: RunnerConfig
    paths: PathsConfig
    upload: UploadConfig
    issue: IssueConfig
    indexing: IndexingConfig
    ui: UiConfig


def _must_get(d: dict[str, Any], key: str) -> Any:
    if key not in d:
        raise KeyError(f"Missing required config key: {key}")
    return d[key]


def load_config(path: Path) -> AppConfig:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    server = raw.get("server", {})
    runner = raw.get("runner", {})
    paths = raw.get("paths", {})
    upload = raw.get("upload", {})
    issue = raw.get("issue", {})
    indexing = raw.get("indexing", {})
    ui = raw.get("ui", {})

    return AppConfig(
        server=ServerConfig(
            host=str(_must_get(server, "host")),
            port=int(_must_get(server, "port")),
        ),
        runner=RunnerConfig(
            command=list(_must_get(runner, "command")),
            default_verbosity=str(_must_get(runner, "default_verbosity")),
            queue_enabled=bool(_must_get(runner, "queue_enabled")),
            runner_config_toml=str(_must_get(runner, "runner_config_toml")),
        ),
        paths=PathsConfig(
            patches_root=str(_must_get(paths, "patches_root")),
            upload_dir=str(_must_get(paths, "upload_dir")),
            allow_crud=bool(_must_get(paths, "allow_crud")),
            crud_allowlist=list(_must_get(paths, "crud_allowlist")),
        ),
        upload=UploadConfig(
            max_bytes=int(_must_get(upload, "max_bytes")),
            allowed_extensions=list(_must_get(upload, "allowed_extensions")),
            ascii_only_names=bool(_must_get(upload, "ascii_only_names")),
        ),
        issue=IssueConfig(
            default_regex=str(_must_get(issue, "default_regex")),
            allocation_start=int(_must_get(issue, "allocation_start")),
            allocation_max=int(_must_get(issue, "allocation_max")),
        ),
        indexing=IndexingConfig(
            log_filename_regex=str(_must_get(indexing, "log_filename_regex")),
            stats_windows_days=list(_must_get(indexing, "stats_windows_days")),
        ),
        ui=UiConfig(
            base_font_px=int(ui.get("base_font_px", 24)),
            drop_overlay_enabled=bool(ui.get("drop_overlay_enabled", True)),
        ),
    )
