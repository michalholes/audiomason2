"""Authoritative AMP policy schema export.

This module provides a deterministic, explicit schema describing the runner Policy
surface that PatchHub may edit.

The schema is derived from dataclasses.fields(Policy) but uses explicit mapping
tables for:
- TOML section placement
- field type categories used by the PatchHub editor
- enum allow-lists

No heuristics are permitted.
"""

from __future__ import annotations

from dataclasses import Field, fields
from typing import Any, get_args, get_origin, get_type_hints

from am_patch.config import Policy

SCHEMA_VERSION = "1"


# Explicit mapping of policy keys to TOML sections.
# Section "" means top-level (no [section] header).
_SECTION_BY_KEY: dict[str, str] = {
    # top-level
    "repo_root": "",
    "patch_dir": "",
    "verbosity": "",
    "log_level": "",
    "json_out": "",
    "console_color": "",
    "ipc_socket_enabled": "",
    "ipc_socket_mode": "",
    "ipc_socket_path": "",
    "ipc_socket_name_template": "",
    "ipc_socket_name": "",
    "ipc_socket_base_dir": "",
    "ipc_socket_system_runtime_dir": "",
    "ipc_socket_cleanup_delay_success_s": "",
    "ipc_socket_cleanup_delay_failure_s": "",
    "ipc_socket_on_startup_exists": "",
    "ipc_socket_on_startup_wait_s": "",
    "unified_patch": "",
    "unified_patch_continue": "",
    "unified_patch_strip": "",
    "unified_patch_touch_on_fail": "",
    "no_op_fail": "",
    "allow_no_op": "",
    "enforce_allowed_files": "",
    "run_all_tests": "",
    "compile_check": "",
    "compile_targets": "",
    "compile_exclude": "",
    "ruff_autofix": "",
    "ruff_autofix_legalize_outside": "",
    "ruff_format": "",
    "gates_allow_fail": "",
    "gates_skip_ruff": "",
    "gates_skip_pytest": "",
    "gates_skip_mypy": "",
    "gates_skip_docs": "",
    "gates_skip_monolith": "",
    "gates_skip_js": "",
    "gate_js_extensions": "",
    "gate_js_command": "",
    "gates_on_partial_apply": "",
    "gates_on_zero_apply": "",
    "gate_docs_include": "",
    "gate_docs_exclude": "",
    "gate_docs_required_files": "",
    "gates_order": "",
    "gate_badguys_runner": "",
    "gate_badguys_command": "",
    "gate_badguys_cwd": "",
    "ruff_targets": "",
    "pytest_targets": "",
    "mypy_targets": "",
    "pytest_use_venv": "",
    "fail_if_live_files_changed": "",
    "live_changed_resolution": "",
    "commit_and_push": "",
    "post_success_audit": "",
    "no_rollback": "",
    "rollback_workspace_on_fail": "",
    "live_repo_guard": "",
    "live_repo_guard_scope": "",
    "audit_rubric_guard": "",
    "patch_jail": "",
    "patch_jail_unshare_net": "",
    "skip_up_to_date": "",
    "allow_non_main": "",
    "allow_push_fail": "",
    "declared_untouched_fail": "",
    "allow_declared_untouched": "",
    "allow_outside_files": "",
    "patch_dir_name": "",
    "patch_layout_logs_dir": "",
    "patch_layout_json_dir": "",
    "patch_layout_workspaces_dir": "",
    "patch_layout_successful_dir": "",
    "patch_layout_unsuccessful_dir": "",
    "lockfile_name": "",
    "current_log_symlink_name": "",
    "current_log_symlink_enabled": "",
    "log_ts_format": "",
    "log_template_issue": "",
    "log_template_finalize": "",
    "failure_zip_name": "",
    "failure_zip_template": "",
    "failure_zip_cleanup_glob_template": "",
    "failure_zip_keep_per_issue": "",
    "failure_zip_delete_on_success_commit": "",
    "failure_zip_log_dir": "",
    "failure_zip_patch_dir": "",
    "workspace_issue_dir_template": "",
    "workspace_repo_dir_name": "",
    "workspace_meta_filename": "",
    "workspace_history_logs_dir": "",
    "workspace_history_oldlogs_dir": "",
    "workspace_history_patches_dir": "",
    "workspace_history_oldpatches_dir": "",
    "blessed_gate_outputs": "",
    "scope_ignore_prefixes": "",
    "scope_ignore_suffixes": "",
    "scope_ignore_contains": "",
    "venv_bootstrap_mode": "",
    "venv_bootstrap_python": "",
    "default_branch": "",
    "success_archive_name": "",
    "success_archive_dir": "",
    "success_archive_cleanup_glob_template": "",
    "success_archive_keep_count": "",
    "require_up_to_date": "",
    "enforce_main_branch": "",
    "update_workspace": "",
    "soft_reset_workspace": "",
    "test_mode": "",
    "test_mode_isolate_patch_dir": "",
    "delete_workspace_on_success": "",
    "ascii_only_patch": "",
    "gate_monolith_enabled": "",
    "gate_monolith_mode": "",
    "gate_monolith_scan_scope": "",
    "gate_monolith_extensions": "",
    "gate_monolith_compute_fanin": "",
    "gate_monolith_on_parse_error": "",
    "gate_monolith_areas": "",
    "gate_monolith_large_loc": "",
    "gate_monolith_huge_loc": "",
    "gate_monolith_large_allow_loc_increase": "",
    "gate_monolith_huge_allow_loc_increase": "",
    "gate_monolith_large_allow_exports_delta": "",
    "gate_monolith_huge_allow_exports_delta": "",
    "gate_monolith_large_allow_imports_delta": "",
    "gate_monolith_huge_allow_imports_delta": "",
    "gate_monolith_new_file_max_loc": "",
    "gate_monolith_new_file_max_exports": "",
    "gate_monolith_new_file_max_imports": "",
    "gate_monolith_hub_fanin_delta": "",
    "gate_monolith_hub_fanout_delta": "",
    "gate_monolith_hub_exports_delta_min": "",
    "gate_monolith_hub_loc_delta_min": "",
    "gate_monolith_crossarea_min_distinct_areas": "",
    "gate_monolith_catchall_basenames": "",
    "gate_monolith_catchall_dirs": "",
    "gate_monolith_catchall_allowlist": "",
}


# Explicit schema type overrides for fields that are not editable via PatchHub.
_READ_ONLY_TYPE_BY_KEY: dict[str, str] = {
    "gate_monolith_areas": "str",
}


# Explicit enum allow-lists for enum-like Policy fields.
_ENUM_BY_KEY: dict[str, list[str]] = {
    "verbosity": ["debug", "verbose", "normal", "quiet"],
    "log_level": ["quiet", "normal", "warning", "verbose", "debug"],
    "console_color": ["auto", "always", "never"],
    "ipc_socket_mode": ["patch_dir", "base_dir", "system_runtime"],
    "ipc_socket_on_startup_exists": ["fail", "wait_then_fail", "unlink_if_stale"],
    "venv_bootstrap_mode": ["auto", "always", "never"],
    "success_archive_dir": ["patch_dir", "successful_dir"],
    "gate_monolith_mode": ["strict", "warn_only", "report_only"],
    "gate_monolith_scan_scope": ["patch", "workspace"],
    "gate_monolith_on_parse_error": ["fail", "warn"],
    "live_changed_resolution": ["fail", "overwrite_live", "overwrite_workspace"],
}


def _infer_schema_type(typ: Any) -> str:
    origin = get_origin(typ)
    args = get_args(typ)

    if typ is bool:
        return "bool"
    if typ is int:
        return "int"
    if typ is str:
        return "str"

    if origin is list and args and args[0] is str:
        return "list[str]"

    # PEP 604 union (e.g., str | None)
    if args and len(args) == 2 and type(None) in args:
        other = args[0] if args[1] is type(None) else args[1]
        if other is str:
            return "optional[str]"
        if other is int:
            return "int"
        if other is bool:
            return "bool"
        if get_origin(other) is list and get_args(other) and get_args(other)[0] is str:
            return "list[str]"

    # Fallback: treat as string surface (read-only paths, complex collections, etc.).
    return "str"


def _get_default_value(field_obj: Field[Any], defaults: Policy) -> Any:
    v = getattr(defaults, field_obj.name)
    return v


def get_policy_schema() -> dict[str, Any]:
    defaults = Policy()
    # Policy uses `from __future__ import annotations`, so Field.type may contain
    # strings. Resolve annotations so type inference is correct.
    hints = get_type_hints(Policy)
    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy": {},
    }

    for f in fields(Policy):
        if f.name == "_src":
            continue

        if f.name not in _SECTION_BY_KEY:
            raise RuntimeError(f"Missing section mapping for policy key: {f.name}")

        type_name = _infer_schema_type(hints.get(f.name, f.type))
        read_only = False
        if f.name in _READ_ONLY_TYPE_BY_KEY:
            type_name = _READ_ONLY_TYPE_BY_KEY[f.name]
            read_only = True

        item: dict[str, Any] = {
            "key": f.name,
            "type": type_name,
            "section": _SECTION_BY_KEY[f.name],
            "default": _get_default_value(f, defaults),
            "label": f.name,
            "help": "",
        }
        if f.name in _ENUM_BY_KEY:
            item["enum"] = list(_ENUM_BY_KEY[f.name])
        if read_only:
            item["read_only"] = True

        out["policy"][f.name] = item

    return out
