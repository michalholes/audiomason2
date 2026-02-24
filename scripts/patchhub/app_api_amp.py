from __future__ import annotations

import json
import os
import tempfile
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any, cast, get_args, get_origin, get_type_hints

from patchhub.app_support import _err, _json_bytes, _ok


def _runner_config_path(repo_root: Path, cfg: Any) -> Path:
    rel = str(getattr(getattr(cfg, "runner", object()), "runner_config_toml", "")).strip()
    if not rel:
        raise ValueError("missing runner_config_toml")
    return (repo_root / rel).resolve()


def _norm_type(tp: object) -> str | None:
    # Policy fields use plain types and optionals (e.g., str | None).
    # We support: bool, int, str, list[str] (and Optional variants of them).
    if tp in (bool, int, str):
        return cast(str, getattr(tp, "__name__", None))

    origin = get_origin(tp)
    args = get_args(tp)

    # Optional[T] / Union[T, None]
    if origin is None and args:
        # PEP 604 union types may expose args without origin.
        non_none = [a for a in args if a is not type(None)]  # noqa: E721
        if len(non_none) == 1:
            return _norm_type(non_none[0])

    if origin in (list,) and len(args) == 1 and args[0] is str:
        return "list_str"

    return None


def _enum_choices(key: str) -> list[str] | None:
    enums: dict[str, list[str]] = {
        "verbosity": ["quiet", "normal", "verbose", "debug"],
        "log_level": ["quiet", "normal", "warning", "verbose", "debug"],
        "console_color": ["auto", "always", "never"],
        "venv_bootstrap_mode": ["auto", "always", "never"],
        "ipc_socket_mode": ["patch_dir", "base_dir", "system_runtime"],
        "ipc_socket_on_startup_exists": ["fail", "reuse", "unlink"],
        "gate_monolith_mode": ["strict", "warn_only", "report_only"],
        "gate_monolith_scan_scope": ["patch", "workspace"],
        "gate_monolith_on_parse_error": ["fail", "warn"],
        "rollback_workspace_on_fail": ["none-applied", "always", "never"],
        "live_changed_resolution": ["fail", "overwrite_live", "overwrite_workspace"],
        "gate_badguys_runner": ["auto", "off", "on"],
    }
    return enums.get(key)


def _policy_fields() -> list[dict[str, Any]]:
    from am_patch.config import Policy

    tmap = get_type_hints(Policy)

    out: list[dict[str, Any]] = []
    for f in fields(Policy):
        if f.name == "_src":
            continue
        tp = tmap.get(f.name, f.type)
        norm = _norm_type(tp)
        if norm is None:
            continue

        enum = _enum_choices(f.name)
        if enum is not None:
            kind = "enum"
        elif norm == "bool":
            kind = "bool"
        elif norm == "int":
            kind = "int"
        elif norm == "str":
            kind = "str"
        else:
            kind = "list_str"

        out.append({"key": f.name, "kind": kind, "enum": enum})

    out.sort(key=lambda d: cast(str, d.get("key", "")))
    return out


def _toml_quote(s: str) -> str:
    return json.dumps(s, ensure_ascii=True)


def _toml_inline_table(d: dict[str, Any]) -> str:
    parts: list[str] = []
    for k in sorted(d.keys()):
        v = d[k]
        parts.append(f"{k} = {_toml_value(v, inline=True)}")
    return "{ " + ", ".join(parts) + " }"


def _toml_list(v: list[Any], *, inline: bool) -> str:
    if not v:
        return "[]"

    if all(isinstance(x, dict) for x in v):
        items = [_toml_inline_table(cast(dict[str, Any], x)) for x in v]
        if inline:
            return "[" + ", ".join(items) + "]"
        inner = ",\n".join(f"  {it}" for it in items)
        return "[\n" + inner + ",\n]"

    items = [_toml_value(x, inline=True) for x in v]
    one = "[" + ", ".join(items) + "]"
    if inline and len(one) <= 88:
        return one
    inner = ",\n".join(f"  {it}" for it in items)
    return "[\n" + inner + ",\n]"


def _toml_value(v: Any, *, inline: bool) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return _toml_quote(v)
    if isinstance(v, list):
        return _toml_list(v, inline=inline)
    if isinstance(v, dict):
        return _toml_inline_table(v)
    return _toml_quote(str(v))


def _dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []

    for k, v in data.items():
        if isinstance(v, dict):
            continue
        lines.append(f"{k} = {_toml_value(v, inline=True)}")

    for sec, sv in data.items():
        if not isinstance(sv, dict):
            continue
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{sec}]")
        for k, v in sv.items():
            lines.append(f"{k} = {_toml_value(v, inline=True)}")

    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


def _coerce_value(kind: str, v: Any) -> Any:
    if kind == "bool":
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off"):
                return False
        raise ValueError("invalid bool")

    if kind == "int":
        if isinstance(v, int):
            return int(v)
        if isinstance(v, str):
            return int(v.strip())
        raise ValueError("invalid int")

    if kind == "list_str":
        if isinstance(v, list):
            out: list[str] = []
            for x in v:
                if not isinstance(x, str):
                    continue
                s = x.strip()
                if s and s not in out:
                    out.append(s)
            return out
        if isinstance(v, str):
            parts = [p.strip() for p in v.split(",")]
            return [p for p in parts if p]
        raise ValueError("invalid list")

    if v is None:
        return ""
    return str(v)


def _key_container(raw: dict[str, Any], key: str) -> dict[str, Any]:
    if key in raw and not isinstance(raw.get(key), dict):
        return raw

    for sec in (
        "paths",
        "git",
        "workspace",
        "scope",
        "gates",
        "promotion",
        "security",
        "logging",
        "audit",
    ):
        sv = raw.get(sec)
        if isinstance(sv, dict) and key in sv and not isinstance(sv.get(key), dict):
            return sv

    if key.startswith("gate_") or key.startswith("gates_"):
        raw.setdefault("gates", {})
        return cast(dict[str, Any], raw["gates"])
    if key.endswith("_targets") or key.startswith(("ruff_", "pytest_", "mypy_")):
        raw.setdefault("security", {})
        return cast(dict[str, Any], raw["security"])
    if key in (
        "commit_and_push",
        "fail_if_live_files_changed",
        "live_changed_resolution",
        "no_rollback",
    ):
        raw.setdefault("promotion", {})
        return cast(dict[str, Any], raw["promotion"])

    return raw


def _read_policy_values(cfg_path: Path) -> dict[str, Any]:
    from am_patch.config import Policy, build_policy, load_config

    tmap = get_type_hints(Policy)

    flat, ok = load_config(cfg_path)
    if not ok:
        flat = {}
    p = build_policy(Policy(), flat)

    out: dict[str, Any] = {}
    for f in fields(Policy):
        if f.name == "_src":
            continue
        tp = tmap.get(f.name, f.type)
        norm = _norm_type(tp)
        if norm is None:
            continue
        v = getattr(p, f.name)
        if v is None:
            if norm in ("str",):
                v = ""
            elif norm == "list_str":
                v = []
            elif norm == "bool":
                v = False
            elif norm == "int":
                v = 0
        out[f.name] = v
    return out


def api_amp_schema(self) -> tuple[int, bytes]:
    return _ok({"schema": {"fields": _policy_fields()}})


def api_amp_config_get(self) -> tuple[int, bytes]:
    try:
        cfg_path = _runner_config_path(self.repo_root, self.cfg)
        values = _read_policy_values(cfg_path)
    except Exception as e:
        return _err(f"amp_config_read_failed: {type(e).__name__}: {e}")
    return _ok({"values": values})


def api_amp_config_post(self, body: dict[str, Any]) -> tuple[int, bytes]:
    from patchhub.job_ids import is_lock_held

    if is_lock_held(self.jail.lock_path()):
        return _json_bytes({"ok": False, "error": "Runner active (lock held)"}, status=409)

    values = body.get("values")
    if not isinstance(values, dict):
        return _err("values must be an object")
    dry_run = bool(body.get("dry_run", False))

    schema = {field["key"]: field for field in _policy_fields()}
    updates: dict[str, Any] = {}
    for k, raw_v in values.items():
        if not isinstance(k, str):
            continue
        if k not in schema:
            continue
        field_spec = schema[k]
        kind = str(field_spec.get("kind", "str"))
        try:
            v = _coerce_value(kind, raw_v)
        except Exception:
            return _err(f"invalid value for {k}")
        enum = field_spec.get("enum")
        if (
            kind == "enum"
            and isinstance(enum, list)
            and enum
            and str(v) not in [str(x) for x in enum]
        ):
            return _err(f"invalid enum for {k}")
        updates[k] = v

    if not updates:
        return _err("no valid fields")

    try:
        cfg_path = _runner_config_path(self.repo_root, self.cfg)
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TypeError("toml root must be a table")

        raw_dict = raw
        for k, v in updates.items():
            c = _key_container(raw_dict, k)
            c[k] = v

        rendered = _dump_toml(raw_dict)

        # Roundtrip validation: parse -> flatten -> build_policy must succeed.
        tmp_obj = tomllib.loads(rendered.encode("utf-8").decode("utf-8"))
        if not isinstance(tmp_obj, dict):
            raise TypeError("toml parse produced non-table")

        from am_patch.config import Policy, build_policy
        from am_patch.config import _flatten_sections as _flat

        flat = _flat(tmp_obj)
        build_policy(Policy(), flat)

        if not dry_run:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=cfg_path.name + ".tmp.",
                dir=str(cfg_path.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out_fp:
                    out_fp.write(rendered)
                os.replace(tmp_name, cfg_path)
            finally:
                try:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
                except Exception:
                    pass

        typed = _read_policy_values(cfg_path)
    except Exception as e:
        return _err(f"amp_config_update_failed: {type(e).__name__}: {e}")

    return _ok({"dry_run": dry_run, "values": typed, "updated": sorted(updates.keys())})
