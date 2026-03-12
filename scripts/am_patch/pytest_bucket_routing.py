from __future__ import annotations

from collections.abc import Mapping, Sequence

from .errors import RunnerError

PYTEST_SMOKE_TARGETS_DEFAULT = [
    "tests/integration/test_all_plugins_loadable.py",
    "tests/test_complete.py",
]

PYTEST_AREA_PREFIXES_DEFAULT = [
    "plugins/audio_processor/",
    "plugins/cover_handler/",
    "plugins/id3_tagger/",
    "plugins/metadata_googlebooks/",
    "plugins/metadata_openlibrary/",
    "plugins/text_utils/",
    "plugins/daemon/",
    "plugins/example_plugin/",
    "plugins/ui_rich/",
    "plugins/test_all_plugin/",
    "plugins/import/",
    "plugins/file_io/",
    "plugins/web_interface/",
    "plugins/cmd_interface/",
    "plugins/diagnostics_console/",
    "plugins/syslog/",
    "plugins/tui/",
    "scripts/am_patch/",
    "scripts/check_patch_pm.py",
    "scripts/patchhub/app_api_amp.py",
    "scripts/patchhub/",
]

PYTEST_AREA_NAMES_DEFAULT = [
    "plugins.audio_processor",
    "plugins.cover_handler",
    "plugins.id3_tagger",
    "plugins.metadata_googlebooks",
    "plugins.metadata_openlibrary",
    "plugins.text_utils",
    "plugins.daemon",
    "plugins.example_plugin",
    "plugins.ui_rich",
    "plugins.test_all_plugin",
    "plugins.import",
    "plugins.file_io",
    "plugins.web_interface",
    "plugins.cmd_interface",
    "plugins.diagnostics_console",
    "plugins.syslog",
    "plugins.tui",
    "runner.am_patch",
    "tooling.check_patch_pm",
    "tooling.patchhub_amp_bridge",
    "tooling.patchhub",
]

PYTEST_AREA_TARGETS_DEFAULT = {
    "plugins.audio_processor": [
        "tests/test_audio_processor_import_conversion_order.py",
    ],
    "plugins.cover_handler": [
        "tests/test_cover_handler_phase1_candidates.py",
    ],
    "plugins.id3_tagger": ["tests/test_id3_tagger_wipe_and_write.py"],
    "plugins.metadata_googlebooks": [],
    "plugins.metadata_openlibrary": [
        "tests/test_metadata_openlibrary_validate_author_title.py",
    ],
    "plugins.text_utils": [],
    "plugins.daemon": ["tests/unit/test_no_pipelineexecutor_bypass.py"],
    "plugins.example_plugin": ["tests/unit/test_plugin_loader_registry.py"],
    "plugins.ui_rich": [],
    "plugins.test_all_plugin": [
        "tests/integration/test_test_all_plugin.py",
        "tests/integration/test_cli_test_all_plugin_commands.py",
    ],
    "plugins.import": [],
    "plugins.file_io": [
        "tests/unit/test_file_io_service.py",
        "tests/test_file_io_import_stage_publish.py",
    ],
    "plugins.web_interface": [
        "tests/test_web_interface_import_ui_openapi_paths.py",
        "tests/unit/test_web_import_wizard.py",
    ],
    "plugins.cmd_interface": ["tests/unit/test_cli_plugin_command_help.py"],
    "plugins.diagnostics_console": ["tests/unit/test_cli_diag_command_stub.py"],
    "plugins.syslog": ["tests/unit/test_cli_diag_command_stub.py"],
    "plugins.tui": [],
    "runner.am_patch": [
        "tests/test_am_patch_gates_wiring_invariant.py",
        "tests/test_scripts_cli_help.py",
    ],
    "tooling.check_patch_pm": ["tests/test_check_patch_pm.py"],
    "tooling.patchhub_amp_bridge": [
        "tests/test_patchhub_api_amp_schema.py",
        "tests/test_patchhub_api_amp_config_roundtrip.py",
    ],
    "tooling.patchhub": [
        "tests/test_patchhub_api_amp_schema.py",
        "tests/test_patchhub_api_amp_config_roundtrip.py",
    ],
}

PYTEST_FAMILY_AREAS_DEFAULT = {
    "import_stack": [
        "plugins.import",
        "plugins.file_io",
        "plugins.web_interface",
    ],
    "observability_cli": [
        "plugins.cmd_interface",
        "plugins.diagnostics_console",
        "plugins.syslog",
    ],
    "tui_stack": ["plugins.tui", "plugins.file_io"],
    "runner_tooling": [
        "runner.am_patch",
        "tooling.check_patch_pm",
        "tooling.patchhub_amp_bridge",
    ],
    "patchhub_ui": ["tooling.patchhub", "tooling.patchhub_amp_bridge"],
}

PYTEST_FAMILY_TARGETS_DEFAULT = {
    "import_stack": [
        "tests/test_file_io_import_stage_publish.py",
        "tests/test_import_default_v3_bootstrap.py",
        "tests/test_import_v3_acceptance_end_to_end.py",
        "tests/test_import_ui_editor_history_bounds.py",
        "tests/test_web_interface_import_ui_openapi_paths.py",
        "tests/unit/test_file_io_service.py",
        "tests/unit/test_import_ui_config_validation_envelope.py",
        "tests/unit/test_web_import_wizard.py",
        (
            "tests/e2e/test_import_ui_flow_editor_e2e.py::"
            "test_import_ui_flow_editor_shell_is_present_and_wired[chromium]"
        ),
        (
            "tests/e2e/test_import_ui_run_wizard_e2e.py::"
            "test_import_ui_run_wizard_happy_path[chromium]"
        ),
        "tests/e2e/test_web_interface_smoke.py::test_import_ui_loads[chromium]",
        (
            "tests/e2e/test_web_interface_app_e2e.py::"
            "test_root_shell_boots_with_expected_script[chromium]"
        ),
    ],
    "observability_cli": [
        "tests/unit/test_cli_diag_command_stub.py",
        "tests/unit/test_cli_plugin_command_help.py",
    ],
    "tui_stack": ["tests/unit/test_file_io_service.py"],
    "runner_tooling": [
        "tests/integration/test_am_patch_smoke_issue666.py::test_am_patch_smoke_issue_666",
        (
            "tests/test_am_patch_subprocess_timeout.py::"
            "test_run_logged_timeout_soft_fail_returns_run_result"
        ),
        ("tests/test_am_patch_subprocess_timeout.py::test_run_logged_timeout_raises_gate_failure"),
        (
            "tests/test_am_patch_ipc_handshake.py::"
            "test_drain_ack_survives_idle_connection_on_same_socket"
        ),
        "tests/test_check_patch_pm.py",
        "tests/test_scripts_cli_help.py",
        "tests/test_am_patch_gates_wiring_invariant.py",
        "tests/test_am_patch_js_gate.py",
        "tests/test_am_patch_config_schema.py",
        "tests/test_am_patch_config_edit_roundtrip.py",
    ],
    "patchhub_ui": [
        "tests/test_patchhub_api_amp_schema.py",
        "tests/test_patchhub_api_amp_config_roundtrip.py",
        (
            "tests/test_patchhub_async_queue_completion.py::"
            "TestPatchhubAsyncQueueForcedCompletion::"
            "test_event_pump_timeout_finalizes_job_and_unblocks_queue"
        ),
        (
            "tests/e2e/test_patchhub_debug_ui_e2e.py::"
            "test_patchhub_debug_ui_flush_and_copy_controls[chromium]"
        ),
    ],
}

PYTEST_BROAD_REPO_PREFIXES_DEFAULT = [
    "src/audiomason/core/",
    "tests/",
    "pytest.ini",
    "pyproject.toml",
    "tests/conftest.py",
    "tests/e2e/conftest.py",
    "tests/e2e/_server_web_interface.py",
    "tests/e2e/_server_patchhub.py",
    "tests/e2e/_asset_inventory.py",
]

PYTEST_BROAD_REPO_TARGETS_DEFAULT = ["tests"]


def _normalize_path(value: str) -> str:
    return str(value).replace("\\", "/").lstrip("./")


def _normalize_prefix(value: str) -> str:
    return _normalize_path(str(value).rstrip("/"))


def _matches_prefix(path: str, prefix: str) -> bool:
    norm_path = _normalize_path(path)
    norm_prefix = _normalize_prefix(prefix)
    return bool(norm_prefix) and (
        norm_path == norm_prefix or norm_path.startswith(norm_prefix + "/")
    )


def _dedupe_keep_first(items: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        norm = str(item).strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _mapping_list(mapping: Mapping[str, object], key: str) -> list[str]:
    raw = mapping.get(key, [])
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def resolve_impacted_areas(
    *,
    decision_paths: Sequence[str],
    pytest_area_prefixes: Sequence[str],
    pytest_area_names: Sequence[str],
) -> list[str]:
    if len(pytest_area_prefixes) != len(pytest_area_names):
        raise RunnerError(
            "CONFIG",
            "INVALID_PYTEST_AREA_MAP",
            "pytest_area_prefixes and pytest_area_names must have the same length",
        )
    areas: list[str] = []
    seen: set[str] = set()
    for path in decision_paths:
        norm_path = _normalize_path(path)
        for prefix, area in zip(pytest_area_prefixes, pytest_area_names, strict=True):
            if _matches_prefix(norm_path, str(prefix)):
                name = str(area).strip()
                if name and name not in seen:
                    seen.add(name)
                    areas.append(name)
                break
    return areas


def resolve_impacted_families(
    *,
    impacted_areas: Sequence[str],
    pytest_family_areas: Mapping[str, object],
) -> list[str]:
    area_set = {str(area).strip() for area in impacted_areas if str(area).strip()}
    families: list[str] = []
    for family, raw_areas in pytest_family_areas.items():
        if not isinstance(raw_areas, list):
            continue
        members = {str(item).strip() for item in raw_areas if str(item).strip()}
        if area_set.intersection(members):
            families.append(str(family).strip())
    return _dedupe_keep_first(families)


def select_pytest_targets(
    *,
    decision_paths: Sequence[str],
    pytest_targets: Sequence[str],
    routing_policy: Mapping[str, object] | None,
) -> list[str]:
    if not routing_policy:
        return list(pytest_targets)

    mode = str(routing_policy.get("pytest_routing_mode", "legacy")).strip() or "legacy"
    if mode == "legacy":
        return list(pytest_targets)
    if mode != "bucketed":
        raise RunnerError(
            "CONFIG",
            "INVALID_PYTEST_ROUTING_MODE",
            f"invalid pytest_routing_mode: {mode!r}",
        )

    smoke_targets = _mapping_list(routing_policy, "pytest_smoke_targets")
    area_prefixes = _mapping_list(routing_policy, "pytest_area_prefixes")
    area_names = _mapping_list(routing_policy, "pytest_area_names")
    area_targets = routing_policy.get("pytest_area_targets", {})
    family_areas = routing_policy.get("pytest_family_areas", {})
    family_targets = routing_policy.get("pytest_family_targets", {})
    broad_prefixes = _mapping_list(routing_policy, "pytest_broad_repo_prefixes")
    broad_targets = _mapping_list(routing_policy, "pytest_broad_repo_targets")

    if not isinstance(area_targets, Mapping):
        area_targets = {}
    if not isinstance(family_areas, Mapping):
        family_areas = {}
    if not isinstance(family_targets, Mapping):
        family_targets = {}

    impacted_areas = resolve_impacted_areas(
        decision_paths=decision_paths,
        pytest_area_prefixes=area_prefixes,
        pytest_area_names=area_names,
    )
    impacted_families = resolve_impacted_families(
        impacted_areas=impacted_areas,
        pytest_family_areas=family_areas,
    )

    selected: list[str] = []
    selected.extend(smoke_targets)
    for area in impacted_areas:
        selected.extend(_mapping_list(area_targets, area))
    for family in impacted_families:
        selected.extend(_mapping_list(family_targets, family))
    if any(_matches_prefix(path, prefix) for path in decision_paths for prefix in broad_prefixes):
        selected.extend(broad_targets)
    return _dedupe_keep_first(selected)
